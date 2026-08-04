from __future__ import annotations

import hashlib
import json
import re
import uuid
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.contracts import (
    CandidateProfile,
    DraftBundle,
    ProviderId,
    ReviewInput,
    RunStatus,
    Stage,
    canonical_hash,
    require_transition,
)
from shared.careerflow_compat import (
    export_pdf,
    extract_jd_emails,
    markdown_to_html,
    safe_attachment_name,
    validate_draft_bundle,
    validate_interview_brief,
)
from shared.errors import ConflictError, NotFoundError, PlatformError

from .credentials import CredentialService
from .models import (
    AgentRunRow,
    ApplicationRow,
    ApprovalRow,
    ArtifactRow,
    CandidateProfileRow,
    ReviewRow,
    ResumeTemplateRow,
    utcnow,
)
from .providers import ProviderClient, SPECS, extract_json
from .research import ResearchFetcher, ResearchSource
from .schemas import ApplicationCreate, InterviewRequest, ProfileExtractRequest
from .settings import Settings
from .storage import ObjectStore


def evidence_from_profile(profile: CandidateProfile) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for experience in profile.experiences:
        for index, claim in enumerate(experience.bullets, 1):
            evidence.append({
                "evidence_id": f"{experience.id}-{index}",
                "source": experience.id,
                "claim": claim,
                "status": "user_confirmed",
            })
    return evidence


def _application_payload(row: ApplicationRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "company": row.company,
        "role": row.role,
        "jd": row.jd,
        "stage": row.stage,
        "history": row.history,
        "draft_bundle": row.draft_bundle,
        "document_plan": row.document_plan,
        "active_output_version": row.active_output_version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


class WorkflowService:
    def __init__(self, settings: Settings, store: ObjectStore | None = None):
        self.settings = settings
        self.providers = ProviderClient(settings.model_timeout_seconds)
        self.credentials = CredentialService(settings)
        self.store = store
        self.research = ResearchFetcher()

    async def get_profile(self, session: AsyncSession, user_id: str) -> CandidateProfileRow | None:
        return await session.get(CandidateProfileRow, user_id)

    async def extract_profile(
        self, session: AsyncSession, user_id: str, request: ProfileExtractRequest
    ) -> dict[str, Any]:
        if not request.consent_to_provider:
            raise PlatformError("provider_consent_required", "Confirm before sending resume text to the provider.")
        existing = await self._idempotent_run(session, user_id, None, request.idempotency_key)
        if existing:
            raise ConflictError("duplicate_run", f"This request already exists with status {existing.status}.")
        key, credential = await self.credentials.resolve(session, user_id, request.session_id, request.provider)
        run = AgentRunRow(
            user_id=user_id,
            run_type="profile_extract",
            provider=request.provider.value,
            model=credential.model or SPECS[request.provider].default_model,
            status=RunStatus.RUNNING.value,
            idempotency_key=request.idempotency_key,
        )
        session.add(run)
        await session.flush()
        prompt = """Extract only facts explicitly present in the resume below. Return one JSON object matching:
{"display_name":"", "headline":"", "education":[{"school":"","program":"","period":"","source_text":""}], "experiences":[{"id":"exp-1","organization":"","role":"","period":"","bullets":[""],"source_text":""}], "skills":[], "uncertainties":[]}.
Do not infer missing names, dates, metrics, employers, tools, or results. Put conflicts and uncertainty in uncertainties.

RESUME:
""" + request.resume_text
        try:
            result = await self.providers.generate(
                request.provider, key, credential.base_url, credential.model, prompt, structured=True
            )
            profile = CandidateProfile.model_validate(extract_json(result.text))
            row = await session.get(CandidateProfileRow, user_id)
            if not row:
                row = CandidateProfileRow(user_id=user_id)
                session.add(row)
            row.profile = profile.model_dump()
            row.evidence = []
            row.confirmed = False
            run.status = RunStatus.SUCCEEDED.value
            run.usage = result.usage
            run.completed_at = utcnow()
            await session.commit()
            return row.profile
        except PlatformError as exc:
            run.status = RunStatus.NEEDS_ATTENTION.value if exc.code == "provider_result_uncertain" else RunStatus.FAILED.value
            run.error_code = exc.code
            run.completed_at = utcnow()
            await session.commit()
            raise

    async def confirm_profile(
        self, session: AsyncSession, user_id: str, profile: CandidateProfile
    ) -> dict[str, Any]:
        row = await session.get(CandidateProfileRow, user_id)
        if not row:
            row = CandidateProfileRow(user_id=user_id)
            session.add(row)
        row.profile = profile.model_dump()
        row.evidence = evidence_from_profile(profile)
        row.confirmed = True
        await session.commit()
        return {"profile": row.profile, "evidence": row.evidence, "confirmed": True}

    async def create_application(
        self, session: AsyncSession, user_id: str, data: ApplicationCreate
    ) -> dict[str, Any]:
        profile = await session.get(CandidateProfileRow, user_id)
        if not profile or not profile.confirmed:
            raise ConflictError("profile_not_confirmed", "Confirm the evidence profile before creating a job.")
        duplicate = await session.execute(
            select(ApplicationRow).where(
                ApplicationRow.user_id == user_id,
                ApplicationRow.company == data.company.strip(),
                ApplicationRow.role == data.role.strip(),
                ApplicationRow.jd == data.jd.strip(),
            )
        )
        if duplicate.scalar_one_or_none():
            raise ConflictError("duplicate_application", "The same company, role, and JD already exist.")
        row = ApplicationRow(
            user_id=user_id,
            company=data.company.strip(),
            role=data.role.strip(),
            jd=data.jd.strip(),
            stage=Stage.CREATED.value,
            history=[{"stage": Stage.CREATED.value, "at": utcnow().isoformat()}],
        )
        session.add(row)
        await session.commit()
        return _application_payload(row)

    async def list_applications(self, session: AsyncSession, user_id: str) -> list[dict[str, Any]]:
        result = await session.execute(
            select(ApplicationRow).where(ApplicationRow.user_id == user_id).order_by(ApplicationRow.updated_at.desc())
        )
        return [_application_payload(row) for row in result.scalars()]

    async def application(self, session: AsyncSession, user_id: str, app_id: str, lock: bool = False) -> ApplicationRow:
        query = select(ApplicationRow).where(ApplicationRow.id == app_id, ApplicationRow.user_id == user_id)
        if lock:
            query = query.with_for_update()
        row = (await session.execute(query)).scalar_one_or_none()
        if not row:
            raise NotFoundError("Application not found.")
        return row

    async def draft(
        self,
        session: AsyncSession,
        user_id: str,
        app_id: str,
        provider: ProviderId,
        session_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        app = await self.application(session, user_id, app_id, lock=True)
        if Stage(app.stage) not in {Stage.CREATED, Stage.DRAFTED}:
            raise ConflictError("stage_blocked", "Drafting is available only before approval.")
        existing = await self._idempotent_run(session, user_id, app_id, idempotency_key)
        if existing:
            raise ConflictError("duplicate_run", f"This request already exists with status {existing.status}.")
        profile = await session.get(CandidateProfileRow, user_id)
        if not profile or not profile.confirmed:
            raise ConflictError("profile_not_confirmed", "The evidence profile is not confirmed.")
        key, credential = await self.credentials.resolve(session, user_id, session_id, provider)
        run = AgentRunRow(
            user_id=user_id,
            application_id=app_id,
            run_type="draft",
            provider=provider.value,
            model=credential.model or SPECS[provider].default_model,
            status=RunStatus.RUNNING.value,
            idempotency_key=idempotency_key,
        )
        session.add(run)
        await session.flush()
        prompt = self._draft_prompt(profile.profile, profile.evidence, app)
        try:
            bundle, usage = await self._generate_draft_with_one_repair(
                provider, key, credential.base_url, credential.model, prompt
            )
            app.draft_bundle = bundle.model_dump()
            app.document_plan = None
            await self._invalidate_approval(session, app)
            self._transition(app, Stage.DRAFTED)
            run.status = RunStatus.SUCCEEDED.value
            run.usage = usage
            run.completed_at = utcnow()
            await session.commit()
            return _application_payload(app)
        except PlatformError as exc:
            run.status = RunStatus.NEEDS_ATTENTION.value if exc.code == "provider_result_uncertain" else RunStatus.FAILED.value
            run.error_code = exc.code
            run.completed_at = utcnow()
            await session.commit()
            raise

    async def edit_draft(
        self, session: AsyncSession, user_id: str, app_id: str, bundle: DraftBundle, document_plan: dict | None
    ) -> dict[str, Any]:
        app = await self.application(session, user_id, app_id, lock=True)
        if Stage(app.stage) not in {Stage.DRAFTED, Stage.APPROVED}:
            raise ConflictError("stage_blocked", "Only drafted content can be edited.")
        self._validate_bundle(bundle)
        app.draft_bundle = bundle.model_dump()
        app.document_plan = document_plan
        await self._invalidate_approval(session, app)
        if Stage(app.stage) != Stage.DRAFTED:
            self._transition(app, Stage.DRAFTED)
        await session.commit()
        return _application_payload(app)

    async def generate_document_plan(
        self,
        session: AsyncSession,
        user_id: str,
        app_id: str,
        provider: ProviderId,
        session_id: str,
        idempotency_key: str,
        template_id: str = "default",
    ) -> dict[str, Any]:
        if not self.store:
            raise PlatformError("storage_unavailable", "Object storage is not configured.", 503)
        app = await self.application(session, user_id, app_id, lock=True)
        if Stage(app.stage) != Stage.DRAFTED or not app.draft_bundle:
            raise ConflictError("stage_blocked", "Generate the draft before creating a document plan.")
        existing_run = await self._idempotent_run(session, user_id, app_id, idempotency_key)
        if existing_run:
            raise ConflictError("duplicate_run", f"This request already exists with status {existing_run.status}.")
        template = (await session.execute(
            select(ResumeTemplateRow).where(
                ResumeTemplateRow.user_id == user_id, ResumeTemplateRow.template_id == template_id
            )
        )).scalar_one_or_none()
        if not template:
            raise NotFoundError("Upload and inspect a source resume before creating a document plan.")
        profile = json.loads((await self.store.get(template.profile_object_key)).decode("utf-8"))
        confirmed = await session.get(CandidateProfileRow, user_id)
        key, credential = await self.credentials.resolve(session, user_id, session_id, provider)
        run = AgentRunRow(
            user_id=user_id, application_id=app_id, run_type="document_plan", provider=provider.value,
            model=credential.model or SPECS[provider].default_model, status=RunStatus.RUNNING.value,
            idempotency_key=idempotency_key,
        )
        session.add(run)
        await session.flush()
        allowed_evidence = {item["evidence_id"] for item in (confirmed.evidence if confirmed else [])}
        prompt = f"""Create a conservative original-format replacement plan. Return ONLY JSON:
{{"template_id":"{template_id}","source_sha256":"{template.source_sha256}","changes":[{{"region_id":"","old_text":"","new_text":"","evidence_ids":[]}}]}}.
Use only listed region IDs. old_text must exactly equal the region text. Change only resume regions supported by approved evidence. Keep PDF replacements short enough for max_width; do not add or delete layout regions. Do not change contact facts unless the approved draft explicitly does so.
REGIONS:\n{json.dumps(profile.get('regions', []), ensure_ascii=False)}
APPROVED CANDIDATE DRAFT:\n{json.dumps(app.draft_bundle, ensure_ascii=False)}
EVIDENCE:\n{json.dumps(confirmed.evidence if confirmed else [], ensure_ascii=False)}"""
        try:
            result = await self.providers.generate(
                provider, key, credential.base_url, credential.model, prompt, structured=True
            )
            from shared.contracts import DocumentPlan
            plan = DocumentPlan.model_validate(extract_json(result.text))
            regions = {str(item["region_id"]): item for item in profile.get("regions", [])}
            for change in plan.changes:
                region = regions.get(change.region_id)
                if not region or change.old_text != region.get("text"):
                    raise PlatformError("document_plan_contract", f"Invalid source region: {change.region_id}")
                if not change.evidence_ids:
                    raise PlatformError("document_plan_contract", f"Every replacement requires evidence: {change.region_id}")
                if any(evidence_id not in allowed_evidence for evidence_id in change.evidence_ids):
                    raise PlatformError("document_plan_contract", f"Unknown evidence ID in {change.region_id}")
            app.document_plan = plan.model_dump()
            await self._invalidate_approval(session, app)
            run.status = RunStatus.SUCCEEDED.value
            run.usage = result.usage
            run.completed_at = utcnow()
            await session.commit()
            return _application_payload(app)
        except PlatformError as exc:
            run.status = RunStatus.NEEDS_ATTENTION.value if exc.code == "provider_result_uncertain" else RunStatus.FAILED.value
            run.error_code = exc.code
            run.completed_at = utcnow()
            await session.commit()
            raise

    async def approve(self, session: AsyncSession, user_id: str, app_id: str) -> dict[str, Any]:
        app = await self.application(session, user_id, app_id, lock=True)
        if Stage(app.stage) != Stage.DRAFTED or not app.draft_bundle:
            raise ConflictError("stage_blocked", "A complete draft is required before approval.")
        has_template = bool(await session.scalar(select(func.count()).select_from(ResumeTemplateRow).where(
            ResumeTemplateRow.user_id == user_id
        )))
        if has_template and not app.document_plan:
            raise ConflictError(
                "document_plan_required",
                "Review and approve an original-format document plan before approving this application.",
            )
        bundle_hash = canonical_hash({"draft": app.draft_bundle, "document_plan": app.document_plan})
        await session.execute(
            delete(ApprovalRow).where(ApprovalRow.application_id == app.id, ApprovalRow.user_id == user_id)
        )
        session.add(ApprovalRow(application_id=app.id, user_id=user_id, bundle_hash=bundle_hash, valid=True))
        self._transition(app, Stage.APPROVED)
        await session.commit()
        return {"application": _application_payload(app), "approval_hash": bundle_hash}

    async def build(
        self, session: AsyncSession, user_id: str, app_id: str, original_artifact_version: str | None = None
    ) -> dict[str, Any]:
        if not self.store:
            raise PlatformError("storage_unavailable", "Object storage is not configured.", 503)
        app = await self.application(session, user_id, app_id, lock=True)
        if Stage(app.stage) != Stage.APPROVED or not app.draft_bundle:
            raise ConflictError("stage_blocked", "Build requires a valid approval.")
        has_template = bool(await session.scalar(select(func.count()).select_from(ResumeTemplateRow).where(
            ResumeTemplateRow.user_id == user_id
        )))
        if has_template and not app.document_plan:
            raise ConflictError("document_plan_required", "The uploaded source resume requires an approved document plan.")
        approval = (await session.execute(
            select(ApprovalRow).where(
                ApprovalRow.application_id == app.id,
                ApprovalRow.user_id == user_id,
                ApprovalRow.valid.is_(True),
            )
        )).scalar_one_or_none()
        current_hash = canonical_hash({"draft": app.draft_bundle, "document_plan": app.document_plan})
        if not approval or approval.bundle_hash != current_hash:
            raise ConflictError("approval_invalid", "The approved content changed. Approve it again.")
        if app.document_plan and not original_artifact_version:
            raise ConflictError("document_build_required", "Use the isolated document build for this application.")
        version = original_artifact_version or str(uuid.uuid4())
        prefix = f"users/{user_id}/applications/{app.id}/output/{version}"
        bundle = DraftBundle.model_validate(app.draft_bundle)
        payloads = {
            "resume.md": (bundle.resume_markdown.encode(), "text/markdown"),
            "cover-letter.md": (bundle.cover_letter_markdown.encode(), "text/markdown"),
            "evidence-map.md": (bundle.evidence_map_markdown.encode(), "text/markdown"),
            "resume.html": (markdown_to_html(bundle.resume_markdown, f"{app.role} - Resume").encode(), "text/html"),
        }
        with tempfile.TemporaryDirectory(prefix="careerflow-generated-") as temp_value:
            pdf_path = Path(temp_value) / "resume.pdf"
            export_pdf(bundle.resume_markdown, pdf_path)
            payloads["resume.pdf"] = (pdf_path.read_bytes(), "application/pdf")
        new_size = sum(len(item[0]) for item in payloads.values())
        user_usage = await session.scalar(
            select(func.coalesce(func.sum(ArtifactRow.size_bytes), 0)).where(ArtifactRow.user_id == user_id)
        )
        global_usage = await session.scalar(select(func.coalesce(func.sum(ArtifactRow.size_bytes), 0)))
        if int(user_usage or 0) + new_size > self.settings.max_user_storage_bytes:
            raise PlatformError("storage_quota", "Building these files would exceed the user storage quota.", 413)
        if int(global_usage or 0) + new_size > int(self.settings.global_storage_capacity_bytes * 0.8):
            raise PlatformError("global_storage_guard", "New artifacts are temporarily paused near the storage limit.", 503)
        staged: list[ArtifactRow] = []
        uploaded_keys: list[str] = []
        try:
            for name, (data, content_type) in payloads.items():
                stored = await self.store.put(f"{prefix}/{name}", data, content_type)
                uploaded_keys.append(stored.key)
                row = ArtifactRow(
                    user_id=user_id,
                    application_id=app.id,
                    kind=name,
                    version_id=version,
                    object_key=stored.key,
                    sha256=stored.sha256,
                    size_bytes=stored.size,
                    content_type=stored.content_type,
                    active=False,
                )
                session.add(row)
                staged.append(row)
            await session.flush()
            await session.execute(
                ArtifactRow.__table__.update()
                .where(
                    ArtifactRow.application_id == app.id,
                    ArtifactRow.user_id == user_id,
                    ArtifactRow.active.is_(True),
                )
                .values(active=False)
            )
            for artifact in staged:
                artifact.active = True
            if original_artifact_version:
                await session.execute(
                    ArtifactRow.__table__.update()
                    .where(
                        ArtifactRow.application_id == app.id,
                        ArtifactRow.user_id == user_id,
                        ArtifactRow.version_id == original_artifact_version,
                    )
                    .values(active=True)
                )
            app.active_output_version = version
            self._transition(app, Stage.BUILT)
            await session.commit()
        except Exception:
            await session.rollback()
            for key in uploaded_keys:
                try:
                    await self.store.delete(key)
                except Exception:
                    pass
            raise
        return {"application": _application_payload(app), "version": version, "artifacts": [a.kind for a in staged]}

    async def delivery(self, session: AsyncSession, user_id: str, app_id: str, recipient: str | None) -> dict[str, Any]:
        app = await self.application(session, user_id, app_id)
        if Stage(app.stage) not in {Stage.BUILT, Stage.SUBMITTED, Stage.INTERVIEWING, Stage.CLOSED}:
            raise ConflictError("stage_blocked", "Build the approved package before preparing email.")
        emails = extract_jd_emails(app.jd)
        if recipient:
            if recipient not in emails:
                raise PlatformError("recipient_not_in_jd", "The recipient must be one of the JD email addresses.")
            selected = recipient
        elif len(emails) == 1:
            selected = emails[0]
        elif not emails:
            raise ConflictError("recipient_missing", "No email address was found in the JD.")
        else:
            return {"requires_selection": True, "recipients": emails}
        profile = await session.get(CandidateProfileRow, user_id)
        name = str((profile.profile if profile else {}).get("display_name", "Candidate"))
        artifacts = list((await session.execute(
            select(ArtifactRow).where(
                ArtifactRow.application_id == app.id,
                ArtifactRow.user_id == user_id,
                ArtifactRow.active.is_(True),
            )
        )).scalars())
        attachment = next((item for item in artifacts if item.kind == "tailored-resume.pdf"), None)
        attachment = attachment or next((item for item in artifacts if item.kind == "tailored-resume.docx"), None)
        attachment = attachment or next((item for item in artifacts if item.kind == "resume.pdf"), None)
        if not attachment or not self.store:
            raise ConflictError("attachment_missing", "No active final resume attachment is available.")
        extension = Path(attachment.kind).suffix.lower()
        attachment_name = safe_attachment_name(f"{name}-{app.role}-Resume", extension)
        base = attachment_name.removesuffix(extension)
        bundle = DraftBundle.model_validate(app.draft_bundle)
        message = EmailMessage()
        message["To"] = selected
        message["Subject"] = base
        body = re.sub(r"^# Cover Letter\s*", "", bundle.cover_letter_markdown).strip()
        message.set_content(body)
        attachment_data = await self.store.get(attachment.object_key)
        if extension == ".pdf":
            message.add_attachment(attachment_data, maintype="application", subtype="pdf", filename=attachment_name)
        else:
            message.add_attachment(
                attachment_data,
                maintype="application",
                subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename=attachment_name,
            )
        eml_data = message.as_bytes()
        if len(eml_data) > self.settings.max_user_storage_bytes:
            raise PlatformError("eml_too_large", "The prepared email exceeds the account storage limit.", 413)
        version = canonical_hash({
            "application": app.id,
            "output_version": app.active_output_version,
            "recipient": selected,
            "attachment_sha256": attachment.sha256,
            "body": body,
        })[:32]
        object_key = f"users/{user_id}/applications/{app.id}/delivery/{version}/application.eml"
        existing_eml = (await session.execute(
            select(ArtifactRow).where(ArtifactRow.object_key == object_key, ArtifactRow.user_id == user_id)
        )).scalar_one_or_none()
        if existing_eml is None:
            user_usage = await session.scalar(
                select(func.coalesce(func.sum(ArtifactRow.size_bytes), 0)).where(ArtifactRow.user_id == user_id)
            )
            global_usage = await session.scalar(select(func.coalesce(func.sum(ArtifactRow.size_bytes), 0)))
            if int(user_usage or 0) + len(eml_data) > self.settings.max_user_storage_bytes:
                raise PlatformError("storage_quota", "Preparing this email would exceed the account storage quota.", 413)
            if int(global_usage or 0) + len(eml_data) > int(self.settings.global_storage_capacity_bytes * 0.8):
                raise PlatformError("global_storage_guard", "New email artifacts are temporarily paused near the storage limit.", 503)
            stored = await self.store.put(object_key, eml_data, "message/rfc822")
            existing_eml = ArtifactRow(
                user_id=user_id,
                application_id=app.id,
                kind="application.eml",
                version_id=version,
                object_key=stored.key,
                sha256=stored.sha256,
                size_bytes=stored.size,
                content_type=stored.content_type,
                active=True,
            )
            session.add(existing_eml)
            await session.flush()
        await session.execute(
            ArtifactRow.__table__.update().where(
                ArtifactRow.application_id == app.id,
                ArtifactRow.user_id == user_id,
                ArtifactRow.kind == "application.eml",
                ArtifactRow.id != existing_eml.id,
            ).values(active=False)
        )
        existing_eml.active = True
        await session.commit()
        return {
            "requires_selection": False,
            "recipient": selected,
            "subject": base,
            "attachment_name": attachment_name,
            "body": body,
            "eml_artifact_id": existing_eml.id,
        }

    async def mark_submitted(self, session: AsyncSession, user_id: str, app_id: str) -> dict[str, Any]:
        app = await self.application(session, user_id, app_id, lock=True)
        if Stage(app.stage) != Stage.BUILT:
            raise ConflictError("stage_blocked", "Only a built application can be marked submitted.")
        self._transition(app, Stage.SUBMITTED)
        await session.commit()
        return _application_payload(app)

    async def interview(
        self, session: AsyncSession, user_id: str, app_id: str, request: InterviewRequest
    ) -> dict[str, Any]:
        app = await self.application(session, user_id, app_id, lock=True)
        if Stage(app.stage) not in {Stage.BUILT, Stage.SUBMITTED, Stage.INTERVIEWING}:
            raise ConflictError("stage_blocked", "Interview preparation starts after build.")
        if request.use_native_search and request.provider not in {ProviderId.OPENAI, ProviderId.QWEN}:
            raise PlatformError("capability_unavailable", "Native search is not approved for this provider.")
        if not request.use_native_search and not request.source_urls:
            raise PlatformError("sources_required", "Provide source URLs or choose an approved native-search provider.")
        existing = await self._idempotent_run(session, user_id, app_id, request.idempotency_key)
        if existing:
            raise ConflictError("duplicate_run", f"This request already exists with status {existing.status}.")
        profile = await session.get(CandidateProfileRow, user_id)
        key, credential = await self.credentials.resolve(session, user_id, request.session_id, request.provider)
        run = AgentRunRow(
            user_id=user_id, application_id=app_id, run_type="interview", provider=request.provider.value,
            model=credential.model or SPECS[request.provider].default_model, status=RunStatus.RUNNING.value,
            idempotency_key=request.idempotency_key,
        )
        session.add(run)
        uploaded_keys: list[str] = []
        try:
            source_urls = [str(url) for url in request.source_urls]
            sources: list[ResearchSource] = []
            if not request.use_native_search:
                sources = await self.research.fetch_all(source_urls)
            prompt = self._interview_prompt(
                app,
                profile.profile if profile else {},
                sources,
                native_search=request.use_native_search,
            )
            result = await self.providers.generate(
                request.provider, key, credential.base_url, credential.model, prompt,
                web_search=request.use_native_search, structured=False, max_output_tokens=12_000,
            )
            try:
                validate_interview_brief(
                    result.text,
                    require_sources=True,
                    allowed_evidence_ids={source.evidence_id for source in sources},
                )
            except ValueError as exc:
                raise PlatformError("provider_contract_error", f"Interview brief failed validation: {exc}") from exc
            version = str(uuid.uuid4())
            if self.store:
                source_manifest = json.dumps(
                    [source.prompt_payload() for source in sources],
                    ensure_ascii=False,
                    indent=2,
                ).encode()
                if sources:
                    source_artifact = await self.store.put(
                        f"users/{user_id}/applications/{app.id}/interview/{version}/research-sources.json",
                        source_manifest,
                        "application/json",
                    )
                    uploaded_keys.append(source_artifact.key)
                    session.add(ArtifactRow(
                        user_id=user_id, application_id=app.id, kind="research-sources.json", version_id=version,
                        object_key=source_artifact.key, sha256=source_artifact.sha256,
                        size_bytes=source_artifact.size, content_type=source_artifact.content_type, active=True,
                    ))
                stored = await self.store.put(
                    f"users/{user_id}/applications/{app.id}/interview/{version}/interview-brief.md",
                    result.text.encode(), "text/markdown"
                )
                uploaded_keys.append(stored.key)
                session.add(ArtifactRow(
                    user_id=user_id, application_id=app.id, kind="interview-brief.md", version_id=version,
                    object_key=stored.key, sha256=stored.sha256, size_bytes=stored.size,
                    content_type=stored.content_type, active=True,
                ))
            if Stage(app.stage) != Stage.INTERVIEWING:
                self._transition(app, Stage.INTERVIEWING)
            run.status = RunStatus.SUCCEEDED.value
            run.usage = result.usage
            run.completed_at = utcnow()
            await session.commit()
            return {"application": _application_payload(app), "brief": result.text}
        except PlatformError as exc:
            for object_key in uploaded_keys:
                try:
                    if self.store:
                        await self.store.delete(object_key)
                except Exception:
                    pass
            run.status = RunStatus.NEEDS_ATTENTION.value if exc.code == "provider_result_uncertain" else RunStatus.FAILED.value
            run.error_code = exc.code
            run.completed_at = utcnow()
            await session.commit()
            raise
        except Exception:
            await session.rollback()
            for object_key in uploaded_keys:
                try:
                    if self.store:
                        await self.store.delete(object_key)
                except Exception:
                    pass
            raise

    async def review(
        self, session: AsyncSession, user_id: str, app_id: str, feedback: ReviewInput
    ) -> dict[str, Any]:
        app = await self.application(session, user_id, app_id, lock=True)
        if Stage(app.stage) not in {Stage.BUILT, Stage.SUBMITTED, Stage.INTERVIEWING, Stage.CLOSED}:
            raise ConflictError("stage_blocked", "Review is available only after build.")
        category = self._review_category(feedback)
        existing = (await session.execute(
            select(ReviewRow).where(ReviewRow.application_id == app.id, ReviewRow.user_id == user_id)
        )).scalar_one_or_none()
        row = existing or ReviewRow(user_id=user_id, application_id=app.id)
        row.outcome = feedback.outcome
        row.raw_feedback = feedback.model_dump()
        row.category = category
        row.coaching = {"next_action": "Use the original feedback to prepare one specific practice exercise."}
        session.add(row)
        if Stage(app.stage) != Stage.CLOSED:
            self._transition(app, Stage.CLOSED)
        await session.commit()
        return {"application": _application_payload(app), "review": row.raw_feedback, "category": category}

    async def aggregate_reviews(self, session: AsyncSession, user_id: str) -> dict[str, list[dict[str, Any]]]:
        rows = (await session.execute(select(ReviewRow).where(ReviewRow.user_id == user_id))).scalars()
        aggregate: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            aggregate.setdefault(row.category, []).append({
                "application_id": row.application_id,
                "outcome": row.outcome,
                "feedback": row.raw_feedback,
                "coaching": row.coaching,
            })
        return aggregate

    async def _generate_draft_with_one_repair(
        self, provider: ProviderId, key: str, base_url: str, model: str, prompt: str
    ) -> tuple[DraftBundle, dict[str, Any]]:
        result = await self.providers.generate(provider, key, base_url, model, prompt, structured=True)
        try:
            bundle = DraftBundle.model_validate(extract_json(result.text))
            self._validate_bundle(bundle)
            return bundle, result.usage
        except (ValueError, PlatformError) as first_error:
            repair = prompt + "\n\nThe previous response failed the required contract. Return ONLY the corrected JSON object. Error: " + str(first_error)
            second = await self.providers.generate(provider, key, base_url, model, repair, structured=True)
            try:
                bundle = DraftBundle.model_validate(extract_json(second.text))
                self._validate_bundle(bundle)
                return bundle, second.usage
            except (ValueError, PlatformError) as exc:
                raise PlatformError("provider_contract_error", f"The model failed the draft contract after one repair: {exc}") from exc

    @staticmethod
    def _validate_bundle(bundle: DraftBundle) -> None:
        try:
            validate_draft_bundle(bundle.as_contract_files())
        except ValueError as exc:
            raise PlatformError("draft_contract_error", str(exc)) from exc

    @staticmethod
    def _draft_prompt(profile: dict[str, Any], evidence: list[dict[str, Any]], app: ApplicationRow) -> str:
        return f"""You are CareerFlow's bounded drafting agent. Use only confirmed evidence. Return exactly one JSON object with keys resume_markdown, cover_letter_markdown, evidence_map_markdown.
Resume headings, exactly once and in order: ## Target, ## Education, ## Relevant Experience, ## Skills.
Cover letter title: # Cover Letter.
Evidence map title: # Evidence Map, followed by ## Claim Mapping and ## JD Gaps. Every material claim must cite an evidence_id. Never invent missing requirements; record them under JD Gaps. Do not output TODO.

PROFILE:\n{json.dumps(profile, ensure_ascii=False)}
EVIDENCE:\n{json.dumps(evidence, ensure_ascii=False)}
COMPANY: {app.company}\nROLE: {app.role}\nFULL JD:\n{app.jd}"""

    @staticmethod
    def _interview_prompt(
        app: ApplicationRow,
        profile: dict[str, Any],
        sources: list[ResearchSource],
        *,
        native_search: bool,
    ) -> str:
        resume = (app.draft_bundle or {}).get("resume_markdown", "")
        evidence = [source.prompt_payload() for source in sources]
        evidence_rule = (
            "Native search citations are not yet independently captured. Do not use any Verified label; "
            "label search-derived statements [Inference] and unresolved statements [Unknown]."
            if native_search
            else "A factual claim may be labelled [Verified:SRC-XX] only when the cited source text below directly supports it. "
            "All other claims must be [Inference] or [Unknown]."
        )
        return f"""Prepare a source-grounded interview brief. Use these exact headings once and in order:
## 1. Evidence Boundary and Research Date
## 2. Company Overview
## 3. Relevant Business Workflow
## 4. JD Decomposition
## 5. Resume-to-Role Map
## 6. Company and Role Questions
## 7. Resume Follow-ups
## 8. Mock Interview and Final Checklist
## 9. Source Ledger
{evidence_rule}
Include each supplied evidence ID, URL, SHA-256 and research date in section 9. Never claim a hiring process is known without direct evidence.
COMPANY: {app.company}\nROLE: {app.role}\nJD:\n{app.jd}\nAPPROVED RESUME:\n{resume}\nPROFILE:\n{json.dumps(profile, ensure_ascii=False)}\nRETRIEVED SOURCE EVIDENCE:\n{json.dumps(evidence, ensure_ascii=False)}"""

    @staticmethod
    def _review_category(feedback: ReviewInput) -> str:
        text = json.dumps(feedback.model_dump(), ensure_ascii=False).lower()
        groups = {
            "knowledge": ["公司", "行业", "业务", "company", "industry"],
            "resume": ["简历", "经历", "项目", "resume", "experience"],
            "behavior": ["沟通", "行为", "冲突", "communication", "behavior"],
            "case": ["案例", "技术", "代码", "case", "technical"],
            "process": ["流程", "通知", "时间", "process", "schedule"],
        }
        scores = {key: sum(term in text for term in terms) for key, terms in groups.items()}
        best = max(scores, key=scores.get)
        return best if scores[best] else "delivery"

    @staticmethod
    async def _idempotent_run(
        session: AsyncSession, user_id: str, app_id: str | None, key: str
    ) -> AgentRunRow | None:
        return (await session.execute(
            select(AgentRunRow).where(
                AgentRunRow.user_id == user_id,
                AgentRunRow.application_id == app_id,
                AgentRunRow.idempotency_key == key,
            )
        )).scalar_one_or_none()

    @staticmethod
    async def _invalidate_approval(session: AsyncSession, app: ApplicationRow) -> None:
        await session.execute(
            ApprovalRow.__table__.update().where(ApprovalRow.application_id == app.id).values(valid=False)
        )

    @staticmethod
    def _transition(app: ApplicationRow, target: Stage) -> None:
        current = Stage(app.stage)
        require_transition(current, target)
        app.stage = target.value
        app.updated_at = utcnow()
        app.history = [*(app.history or []), {"stage": target.value, "at": app.updated_at.isoformat()}]
