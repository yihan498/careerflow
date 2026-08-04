from __future__ import annotations

import hashlib
import io
import json
import re
import secrets
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import ConflictError, NotFoundError, PlatformError

from .models import ArtifactRow, DocumentJobRow, ResumeTemplateRow
from .security import DocumentTokenSigner
from .settings import Settings
from .storage import ObjectStore


SAFE_OUTPUT_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,199}$")
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".json": "application/json",
    ".png": "image/png",
    ".txt": "text/plain",
}


class DocumentJobService:
    def __init__(self, settings: Settings, store: ObjectStore):
        self.settings = settings
        self.store = store
        self.signer = DocumentTokenSigner(settings.document_token_secret)

    async def inspect_upload(
        self, session: AsyncSession, user_id: str, upload: UploadFile
    ) -> dict[str, Any]:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in {".pdf", ".docx"}:
            raise PlatformError("unsupported_document", "Only PDF and DOCX files are accepted.")
        data = await upload.read(self.settings.max_source_file_bytes + 1)
        if len(data) > self.settings.max_source_file_bytes:
            raise PlatformError("file_too_large", "The source resume exceeds 10 MB.", 413)
        self._check_magic(data, suffix)
        usage = await session.scalar(
            select(func.coalesce(func.sum(ArtifactRow.size_bytes), 0)).where(ArtifactRow.user_id == user_id)
        )
        if int(usage or 0) + len(data) > self.settings.max_user_storage_bytes:
            raise PlatformError("storage_quota", "The user storage quota would be exceeded.", 413)
        global_usage = await session.scalar(select(func.coalesce(func.sum(ArtifactRow.size_bytes), 0)))
        if int(global_usage or 0) + len(data) > int(self.settings.global_storage_capacity_bytes * 0.8):
            raise PlatformError("global_storage_guard", "New uploads are temporarily paused near the storage limit.", 503)
        source_sha = hashlib.sha256(data).hexdigest()
        source_version = secrets.token_hex(16)
        source_key = f"users/{user_id}/profile/source/{source_version}/source{suffix}"
        stored = await self.store.put(source_key, data, CONTENT_TYPES[suffix])
        source_artifact = ArtifactRow(
            user_id=user_id, application_id=None, kind=f"source-resume{suffix}", version_id=source_version,
            object_key=stored.key, sha256=stored.sha256, size_bytes=stored.size,
            content_type=stored.content_type, active=False,
        )
        session.add(source_artifact)
        await session.flush()
        job, token = await self._new_job(
            session, user_id, None, "inspect", source_sha,
            {"source_object_key": source_key, "source_artifact_id": source_artifact.id, "source_filename": f"source{suffix}"},
        )
        await session.commit()
        response = await self._call_worker(job, token, source_key, f"source{suffix}")
        await session.refresh(job)
        if job.status != "succeeded":
            raise PlatformError("document_job_failed", "The isolated document inspection did not complete.", 502)
        profile_key = f"{job.output_prefix}/document-profile.json"
        profile = json.loads((await self.store.get(profile_key)).decode("utf-8"))
        existing = (await session.execute(
            select(ResumeTemplateRow).where(
                ResumeTemplateRow.user_id == user_id, ResumeTemplateRow.template_id == "default"
            )
        )).scalar_one_or_none()
        if existing:
            await session.delete(existing)
        template = ResumeTemplateRow(
            user_id=user_id,
            template_id="default",
            source_object_key=source_key,
            profile_object_key=profile_key,
            source_sha256=source_sha,
            source_filename=f"source{suffix}",
            document_format=profile["format"],
        )
        session.add(template)
        source_artifact.active = True
        await session.commit()
        extracted_key = f"{job.output_prefix}/extracted-text.txt"
        extracted = (await self.store.get(extracted_key)).decode("utf-8", errors="replace")
        return {"job_id": job.id, "template": profile, "extracted_text": extracted, "worker": response}

    async def build_application_document(
        self, session: AsyncSession, user_id: str, application_id: str, plan: dict[str, Any]
    ) -> str:
        template = (await session.execute(
            select(ResumeTemplateRow).where(
                ResumeTemplateRow.user_id == user_id, ResumeTemplateRow.template_id == plan.get("template_id")
            )
        )).scalar_one_or_none()
        if not template:
            raise NotFoundError("Resume template not found.")
        if plan.get("source_sha256") != template.source_sha256:
            raise ConflictError("source_changed", "The document plan targets a different source resume.")
        global_usage = await session.scalar(select(func.coalesce(func.sum(ArtifactRow.size_bytes), 0)))
        if int(global_usage or 0) > int(self.settings.global_storage_capacity_bytes * 0.9):
            raise PlatformError("preview_storage_guard", "Document previews are paused near the storage limit.", 503)
        source = await self.store.get(template.source_object_key)
        profile = await self.store.get(template.profile_object_key)
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(template.source_filename, source)
            archive.writestr("document-profile.json", profile)
            archive.writestr("document-plan.json", json.dumps(plan, ensure_ascii=False))
        package_data = package.getvalue()
        package_sha = hashlib.sha256(package_data).hexdigest()
        package_key = f"users/{user_id}/applications/{application_id}/document-input/{secrets.token_hex(16)}.zip"
        await self.store.put(package_key, package_data, "application/zip")
        job, token = await self._new_job(
            session, user_id, application_id, "build", package_sha,
            {"source_object_key": package_key, "source_filename": "input.zip"},
        )
        await session.commit()
        await self._call_worker(job, token, package_key, "input.zip")
        await session.refresh(job)
        if job.status != "succeeded":
            raise PlatformError("document_job_failed", "The isolated document build did not complete.", 502)
        return job.id

    async def consume(
        self, session: AsyncSession, token: str
    ) -> tuple[DocumentJobRow, str]:
        try:
            claims = self.signer.verify(token)
        except Exception as exc:
            raise PlatformError("invalid_document_token", "Document token is invalid.", 401) from exc
        row = (await session.execute(
            select(DocumentJobRow).where(DocumentJobRow.id == claims.job_id).with_for_update()
        )).scalar_one_or_none()
        if not row or row.token_jti != claims.jti:
            raise PlatformError("invalid_document_token", "Document job does not match the token.", 401)
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if row.consumed or expires <= datetime.now(timezone.utc):
            raise ConflictError("document_token_used", "Document token was used or expired.")
        if row.action != claims.action or row.source_sha256 != claims.source_sha256:
            raise PlatformError("invalid_document_token", "Document token claims do not match the job.", 401)
        row.consumed = True
        row.status = "running"
        await session.commit()
        return row

    async def upload_url(
        self, session: AsyncSession, job_id: str, name: str, content_type: str
    ) -> dict[str, str]:
        if not SAFE_OUTPUT_NAME.fullmatch(name):
            raise PlatformError("unsafe_output_name", "Worker output name is not allowed.")
        row = await session.get(DocumentJobRow, job_id)
        if not row or row.status != "running":
            raise ConflictError("document_job_inactive", "Document job is not running.")
        key = f"{row.output_prefix}/{name}"
        return {"key": key, "url": self.store.signed_put(key, content_type, 300)}

    async def complete(
        self, session: AsyncSession, job_id: str, files: list[dict[str, Any]], result: dict[str, Any]
    ) -> None:
        row = (await session.execute(
            select(DocumentJobRow).where(DocumentJobRow.id == job_id).with_for_update()
        )).scalar_one_or_none()
        if not row or row.status != "running":
            raise ConflictError("document_job_inactive", "Document job is not running.")
        for item in files:
            name = str(item["name"])
            key = f"{row.output_prefix}/{name}"
            head = await self.store.head(key)
            if int(head["ContentLength"]) != int(item["size"]):
                raise ConflictError("document_output_mismatch", f"Uploaded size differs for {name}.")
            actual = await self.store.get(key)
            if hashlib.sha256(actual).hexdigest() != str(item["sha256"]):
                raise ConflictError("document_output_mismatch", f"Uploaded hash differs for {name}.")
            session.add(ArtifactRow(
                user_id=row.user_id, application_id=row.application_id, kind=name, version_id=row.id,
                object_key=key, sha256=str(item["sha256"]), size_bytes=int(item["size"]),
                content_type=str(item["content_type"]), active=False,
            ))
        row.status = "succeeded"
        row.result = {**row.result, **result, "files": files}
        await session.commit()

    async def fail(self, session: AsyncSession, job_id: str, code: str) -> None:
        row = await session.get(DocumentJobRow, job_id)
        if row:
            row.status = "failed"
            row.result = {**row.result, "error_code": code}
            await session.commit()

    async def _new_job(
        self, session: AsyncSession, user_id: str, application_id: str | None, action: str,
        source_sha: str, initial_result: dict[str, Any]
    ) -> DocumentJobRow:
        job = DocumentJobRow(
            user_id=user_id,
            application_id=application_id,
            action=action,
            source_sha256=source_sha,
            token_jti="pending",
            output_prefix=f"users/{user_id}/" + (
                f"applications/{application_id}/document-output/pending" if application_id else "profile/template-output/pending"
            ),
            result=initial_result,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        session.add(job)
        await session.flush()
        token, jti = self.signer.issue(job.id, action, source_sha, 600)
        job.token_jti = jti
        job.output_prefix = f"users/{user_id}/" + (
            f"applications/{application_id}/document-output/{job.id}" if application_id else f"profile/template-output/{job.id}"
        )
        return job, token

    async def _call_worker(self, job: DocumentJobRow, token: str, source_key: str, filename: str) -> dict[str, Any]:
        payload = {
            "token": token,
            "job_id": job.id,
            "action": job.action,
            "source_url": self.store.signed_get(source_key, 600),
            "source_filename": filename,
            "callback_base_url": (self.settings.document_callback_base_url or self.settings.app_origin).rstrip("/"),
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.document_timeout_seconds) as client:
                response = await client.post(f"{self.settings.document_worker_url.rstrip('/')}/v1/jobs", json=payload)
            if response.status_code >= 400:
                raise PlatformError("document_worker_error", f"Document worker returned HTTP {response.status_code}.", 502)
            return response.json()
        except httpx.TimeoutException as exc:
            raise PlatformError("document_result_uncertain", "The document worker timed out; do not assume success.", 504) from exc

    @staticmethod
    def _check_magic(data: bytes, suffix: str) -> None:
        if suffix == ".pdf" and not data.startswith(b"%PDF-"):
            raise PlatformError("file_type_mismatch", "The uploaded file is not a valid PDF.")
        if suffix == ".docx" and not data.startswith(b"PK"):
            raise PlatformError("file_type_mismatch", "The uploaded file is not a valid DOCX archive.")
