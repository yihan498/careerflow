from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

import httpx
import secrets

from fastapi import Depends, FastAPI, File, Header, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.contracts import CandidateProfile, ProviderId
from shared.errors import PlatformError

from .auth import CurrentUser, current_user
from .credentials import CredentialService
from .db import get_session, init_db
from .document_jobs import DocumentJobService
from .models import (
    ApplicationRow,
    ArtifactRow,
    AgentRunRow,
    ApprovalRow,
    CandidateProfileRow,
    DocumentJobRow,
    ProviderCredentialRow,
    ResumeTemplateRow,
    ReviewRow,
)
from .maintenance import maintenance_loop
from .providers import ProviderClient, SPECS
from .schemas import (
    ApplicationCreate,
    DraftEdit,
    DraftRequest,
    DocumentPlanRequest,
    InterviewRequest,
    ProfileConfirm,
    ProfileExtractRequest,
    ProviderCredentialInput,
    ReviewRequest,
)
from .settings import Settings, get_settings
from .storage import ObjectStore
from .workflows import WorkflowService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()
    app.state.settings = settings
    app.state.store = ObjectStore(settings) if settings.r2_access_key_id else None
    app.state.workflow = WorkflowService(settings, app.state.store)
    app.state.documents = DocumentJobService(settings, app.state.store) if app.state.store else None
    cleanup = asyncio.create_task(maintenance_loop(settings, app.state.store))
    try:
        yield
    finally:
        cleanup.cancel()
        try:
            await cleanup
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="CareerFlow Web API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
settings = get_settings()
origins = settings.cors_origins or [settings.app_origin]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Dev-User"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://challenges.cloudflare.com; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "connect-src 'self' https://*.supabase.co https://challenges.cloudflare.com; "
        "frame-src https://challenges.cloudflare.com; frame-ancestors 'none'"
    )
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


rate_windows: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def bounded_rate_limit(request: Request, call_next):
    path = request.url.path
    protected = any(part in path for part in ("/providers/test", "/profile/resume", "/draft", "/interview", "/document-"))
    if protected and request.method in {"POST", "PUT"}:
        address = request.client.host if request.client else "unknown"
        key = f"{address}:{path.rsplit('/', 1)[-1]}"
        now = monotonic()
        bucket = rate_windows[key]
        while bucket and bucket[0] < now - 3600:
            bucket.popleft()
        if len(bucket) >= 30:
            return JSONResponse(status_code=429, content={"error": {"code": "rate_limit", "message": "Too many requests. Try again later."}})
        bucket.append(now)
    return await call_next(request)


@app.exception_handler(PlatformError)
async def platform_error_handler(_: Request, exc: PlatformError):
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


def workflow(request: Request) -> WorkflowService:
    return request.app.state.workflow


def documents(request: Request) -> DocumentJobService:
    service = request.app.state.documents
    if not service:
        raise PlatformError("storage_unavailable", "Document storage is not configured.", 503)
    return service


def verify_worker_secret(value: str | None, settings: Settings) -> None:
    if not value or not secrets.compare_digest(value, settings.document_worker_shared_secret):
        raise PlatformError("worker_authentication", "Worker authentication failed.", 401)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "web-api"}


@app.get("/api/v1/providers")
async def providers(_: CurrentUser = Depends(current_user)):
    return {
        "data": [
            {
                "id": spec.id.value,
                "label": spec.label,
                "default_base_url": spec.default_base_url,
                "default_model": spec.default_model,
                "capabilities": sorted(item.value for item in spec.capabilities),
                "requires_endpoint_id": spec.requires_endpoint_id,
            }
            for spec in SPECS.values()
        ]
    }


@app.post("/api/v1/providers/test")
async def test_provider(
    data: ProviderCredentialInput,
    user: CurrentUser = Depends(current_user),
    service: WorkflowService = Depends(workflow),
):
    result = await service.providers.test_connection(data.provider, data.api_key, data.base_url, data.model)
    return {"data": {"ok": True, "provider": data.provider.value, "model": result.model, "usage": result.usage}}


@app.put("/api/v1/providers/session")
async def save_provider(
    data: ProviderCredentialInput,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    await service.providers.test_connection(data.provider, data.api_key, data.base_url, data.model)
    row = await service.credentials.save(
        session, user.id, data.session_id, data.provider, data.api_key, data.base_url, data.model, data.save
    )
    await session.commit()
    return {"data": {"provider": row.provider, "saved": row.persistent, "last_four": row.key_last_four}}


@app.delete("/api/v1/providers/{provider}", status_code=204)
async def delete_provider(
    provider: ProviderId,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    await service.credentials.delete(session, user.id, provider)
    await session.commit()
    return Response(status_code=204)


@app.get("/api/v1/profile")
async def get_profile(
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(CandidateProfileRow, user.id)
    return {"data": None if not row else {"profile": row.profile, "evidence": row.evidence, "confirmed": row.confirmed}}


@app.post("/api/v1/profile/resume")
async def upload_resume(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: DocumentJobService = Depends(documents),
):
    return {"data": await service.inspect_upload(session, user.id, file)}


@app.post("/api/v1/profile/extract")
async def extract_profile(
    data: ProfileExtractRequest,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    return {"data": await service.extract_profile(session, user.id, data)}


@app.post("/api/v1/profile/confirm")
async def confirm_profile(
    data: ProfileConfirm,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    return {"data": await service.confirm_profile(session, user.id, data.profile)}


@app.post("/api/v1/applications", status_code=201)
async def create_application(
    data: ApplicationCreate,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    return {"data": await service.create_application(session, user.id, data)}


@app.get("/api/v1/applications")
async def list_applications(
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    return {"data": await service.list_applications(session, user.id)}


@app.get("/api/v1/applications/{app_id}")
async def get_application(
    app_id: str,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    row = await service.application(session, user.id, app_id)
    return {"data": {
        "id": row.id, "company": row.company, "role": row.role, "jd": row.jd, "stage": row.stage,
        "history": row.history, "draft_bundle": row.draft_bundle, "document_plan": row.document_plan,
        "active_output_version": row.active_output_version,
    }}


@app.post("/api/v1/applications/{app_id}/draft")
async def draft_application(
    app_id: str,
    data: DraftRequest,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    return {"data": await service.draft(
        session, user.id, app_id, data.provider, data.session_id, data.idempotency_key
    )}


@app.put("/api/v1/applications/{app_id}/draft")
async def edit_application_draft(
    app_id: str,
    data: DraftEdit,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    plan = data.document_plan.model_dump() if data.document_plan else None
    return {"data": await service.edit_draft(session, user.id, app_id, data.bundle, plan)}


@app.post("/api/v1/applications/{app_id}/document-plan")
async def create_document_plan(
    app_id: str,
    data: DocumentPlanRequest,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    return {"data": await service.generate_document_plan(
        session, user.id, app_id, data.provider, data.session_id, data.idempotency_key, data.template_id
    )}


@app.post("/api/v1/applications/{app_id}/approve")
async def approve_application(
    app_id: str,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    return {"data": await service.approve(session, user.id, app_id)}


@app.post("/api/v1/applications/{app_id}/build")
async def build_application(
    app_id: str,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    return {"data": await service.build(session, user.id, app_id)}


@app.post("/api/v1/applications/{app_id}/document-build")
async def build_application_document(
    app_id: str,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    workflow_service: WorkflowService = Depends(workflow),
    document_service: DocumentJobService = Depends(documents),
):
    application = await workflow_service.application(session, user.id, app_id)
    if application.stage != "approved" or not application.document_plan:
        raise PlatformError("stage_blocked", "An approved document plan is required.", 409)
    version = await document_service.build_application_document(
        session, user.id, app_id, application.document_plan
    )
    return {"data": await workflow_service.build(session, user.id, app_id, version)}


@app.get("/api/v1/applications/{app_id}/delivery")
async def prepare_delivery(
    app_id: str,
    recipient: str | None = None,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    return {"data": await service.delivery(session, user.id, app_id, recipient)}


@app.post("/api/v1/applications/{app_id}/submitted")
async def mark_submitted(
    app_id: str,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    return {"data": await service.mark_submitted(session, user.id, app_id)}


@app.post("/api/v1/applications/{app_id}/interview")
async def prepare_interview(
    app_id: str,
    data: InterviewRequest,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    return {"data": await service.interview(session, user.id, app_id, data)}


@app.post("/api/v1/applications/{app_id}/review")
async def record_review(
    app_id: str,
    data: ReviewRequest,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    return {"data": await service.review(session, user.id, app_id, data.feedback)}


@app.get("/api/v1/reviews")
async def reviews(
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    service: WorkflowService = Depends(workflow),
):
    return {"data": await service.aggregate_reviews(session, user.id)}


@app.get("/api/v1/artifacts/{artifact_id}/download")
async def artifact_download(
    artifact_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    row = (await session.execute(
        select(ArtifactRow).where(ArtifactRow.id == artifact_id, ArtifactRow.user_id == user.id)
    )).scalar_one_or_none()
    if not row:
        raise PlatformError("not_found", "Artifact not found.", 404)
    store: ObjectStore | None = request.app.state.store
    if not store:
        raise PlatformError("storage_unavailable", "Object storage is not configured.", 503)
    return {"data": {"url": store.signed_get(row.object_key, 120, row.kind), "content_type": row.content_type}}


@app.get("/api/v1/applications/{app_id}/artifacts")
async def application_artifacts(
    app_id: str,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    exists = await session.scalar(select(func.count()).select_from(ApplicationRow).where(
        ApplicationRow.id == app_id, ApplicationRow.user_id == user.id
    ))
    if not exists:
        raise PlatformError("not_found", "Application not found.", 404)
    rows = (await session.execute(
        select(ArtifactRow).where(
            ArtifactRow.application_id == app_id,
            ArtifactRow.user_id == user.id,
            ArtifactRow.active.is_(True),
        ).order_by(ArtifactRow.kind)
    )).scalars()
    return {"data": [{
        "id": row.id, "kind": row.kind, "size_bytes": row.size_bytes,
        "sha256": row.sha256, "content_type": row.content_type,
    } for row in rows]}


@app.delete("/api/v1/account", status_code=204)
async def delete_account(
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    store: ObjectStore | None = request.app.state.store
    if store:
        await store.delete_prefix(f"users/{user.id}/")
    await session.execute(delete(ReviewRow).where(ReviewRow.user_id == user.id))
    await session.execute(delete(ApprovalRow).where(ApprovalRow.user_id == user.id))
    await session.execute(delete(AgentRunRow).where(AgentRunRow.user_id == user.id))
    await session.execute(delete(DocumentJobRow).where(DocumentJobRow.user_id == user.id))
    await session.execute(delete(ArtifactRow).where(ArtifactRow.user_id == user.id))
    await session.execute(delete(ProviderCredentialRow).where(ProviderCredentialRow.user_id == user.id))
    await session.execute(delete(ResumeTemplateRow).where(ResumeTemplateRow.user_id == user.id))
    await session.execute(delete(ApplicationRow).where(ApplicationRow.user_id == user.id))
    await session.execute(delete(CandidateProfileRow).where(CandidateProfileRow.user_id == user.id))
    await session.commit()
    settings = request.app.state.settings
    if settings.supabase_url and settings.supabase_service_role_key:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.delete(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user.id}",
                headers={"Authorization": f"Bearer {settings.supabase_service_role_key}", "apikey": settings.supabase_service_role_key},
            )
        if response.status_code >= 400 and response.status_code != 404:
            raise PlatformError("auth_deletion_pending", "Application data was deleted, but account removal must be retried.", 502)
    return Response(status_code=204)


@app.get("/api/v1/account/export")
async def export_account(
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    profile = await session.get(CandidateProfileRow, user.id)
    applications = list((await session.execute(
        select(ApplicationRow).where(ApplicationRow.user_id == user.id)
    )).scalars())
    reviews = list((await session.execute(select(ReviewRow).where(ReviewRow.user_id == user.id))).scalars())
    artifacts = list((await session.execute(select(ArtifactRow).where(ArtifactRow.user_id == user.id))).scalars())
    store: ObjectStore | None = request.app.state.store
    return {"data": {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profile": None if not profile else {"profile": profile.profile, "evidence": profile.evidence, "confirmed": profile.confirmed},
        "applications": [{"id": row.id, "company": row.company, "role": row.role, "jd": row.jd, "stage": row.stage, "history": row.history, "draft_bundle": row.draft_bundle, "document_plan": row.document_plan} for row in applications],
        "reviews": [{"application_id": row.application_id, "outcome": row.outcome, "feedback": row.raw_feedback, "category": row.category} for row in reviews],
        "artifacts": [{"kind": row.kind, "sha256": row.sha256, "size_bytes": row.size_bytes, "download_url": store.signed_get(row.object_key, 900, row.kind) if store else None} for row in artifacts],
    }}


@app.delete("/api/v1/applications/{app_id}", status_code=204)
async def delete_application(
    app_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    row = (await session.execute(select(ApplicationRow).where(
        ApplicationRow.id == app_id, ApplicationRow.user_id == user.id
    ))).scalar_one_or_none()
    if not row:
        raise PlatformError("not_found", "Application not found.", 404)
    store: ObjectStore | None = request.app.state.store
    if store:
        await store.delete_prefix(f"users/{user.id}/applications/{app_id}/")
    await session.delete(row)
    await session.commit()
    return Response(status_code=204)


@app.post("/api/internal/document-jobs/consume")
async def consume_document_job(
    body: dict,
    x_worker_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    service: DocumentJobService = Depends(documents),
    settings: Settings = Depends(get_settings),
):
    verify_worker_secret(x_worker_secret, settings)
    row = await service.consume(session, str(body.get("token", "")))
    return {"data": {"job_id": row.id, "action": row.action, "source_sha256": row.source_sha256}}


@app.post("/api/internal/document-jobs/{job_id}/upload-url")
async def document_output_url(
    job_id: str,
    body: dict,
    x_worker_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    service: DocumentJobService = Depends(documents),
    settings: Settings = Depends(get_settings),
):
    verify_worker_secret(x_worker_secret, settings)
    return {"data": await service.upload_url(
        session, job_id, str(body.get("name", "")), str(body.get("content_type", "application/octet-stream"))
    )}


@app.post("/api/internal/document-jobs/{job_id}/complete")
async def complete_document_job(
    job_id: str,
    body: dict,
    x_worker_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    service: DocumentJobService = Depends(documents),
    settings: Settings = Depends(get_settings),
):
    verify_worker_secret(x_worker_secret, settings)
    await service.complete(session, job_id, list(body.get("files", [])), dict(body.get("result", {})))
    return {"data": {"status": "succeeded"}}


@app.post("/api/internal/document-jobs/{job_id}/fail")
async def fail_document_job(
    job_id: str,
    body: dict,
    x_worker_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    service: DocumentJobService = Depends(documents),
    settings: Settings = Depends(get_settings),
):
    verify_worker_secret(x_worker_secret, settings)
    await service.fail(session, job_id, str(body.get("error_code", "worker_failed")))
    return {"data": {"status": "failed"}}


frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
