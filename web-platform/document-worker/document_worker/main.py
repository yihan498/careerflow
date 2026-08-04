from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
import jwt
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=40, max_length=4_000)
    job_id: str = Field(min_length=1, max_length=100)
    action: Literal["inspect", "build"]
    source_url: HttpUrl
    source_filename: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,199}$")


app = FastAPI(
    title="CareerFlow Isolated Document Worker",
    docs_url=None,
    redoc_url=None,
    openapi_url=None if os.environ.get("ENVIRONMENT", "development").lower() == "production" else "/openapi.json",
)
WORKER_SECRET = os.environ.get("DOCUMENT_WORKER_SHARED_SECRET", "")
WORKER_REQUEST_SECRET = os.environ.get("DOCUMENT_WORKER_REQUEST_SECRET", "")
DOCUMENT_TOKEN_SECRET = os.environ.get("DOCUMENT_TOKEN_SECRET", "")
CALLBACK_BASE_URL = os.environ.get("DOCUMENT_CALLBACK_BASE_URL", "").rstrip("/")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
SOURCE_ORIGINS = {
    value.strip().rstrip("/")
    for value in os.environ.get(
        "DOCUMENT_SOURCE_ORIGINS",
        "" if ENVIRONMENT == "production" else "http://minio:9000",
    ).split(",")
    if value.strip()
}
MAX_DOWNLOAD_BYTES = int(os.environ.get("MAX_DOCUMENT_DOWNLOAD_BYTES", str(24 * 1024 * 1024)))
RUNNER_TIMEOUT = int(os.environ.get("DOCUMENT_RUNNER_TIMEOUT_SECONDS", "180"))
MAX_OUTPUT_FILES = 12
MAX_OUTPUT_BYTES = 20 * 1024 * 1024


def worker_headers() -> dict[str, str]:
    if len(WORKER_SECRET) < 16:
        raise RuntimeError("DOCUMENT_WORKER_SHARED_SECRET is not configured")
    return {"X-Worker-Secret": WORKER_SECRET}


def require_request_secret(value: str | None) -> None:
    if len(WORKER_REQUEST_SECRET) < 16 or not value or not secrets.compare_digest(value, WORKER_REQUEST_SECRET):
        raise PermissionError("document worker request authentication failed")


def verify_job_token(token: str) -> dict:
    if len(DOCUMENT_TOKEN_SECRET) < 32:
        raise RuntimeError("DOCUMENT_TOKEN_SECRET is not configured")
    return jwt.decode(
        token,
        DOCUMENT_TOKEN_SECRET,
        algorithms=["HS256"],
        audience="careerflow-document-worker",
    )


def validate_fixed_endpoints() -> None:
    callback = urlsplit(CALLBACK_BASE_URL)
    if not CALLBACK_BASE_URL or callback.scheme not in {"http", "https"} or not callback.hostname:
        raise RuntimeError("DOCUMENT_CALLBACK_BASE_URL must be a fixed HTTP(S) origin")
    if callback.username or callback.password or callback.query or callback.fragment:
        raise RuntimeError("DOCUMENT_CALLBACK_BASE_URL must not contain credentials, query, or fragment")
    if ENVIRONMENT == "production" and callback.scheme != "https":
        raise RuntimeError("DOCUMENT_CALLBACK_BASE_URL must use HTTPS in production")
    for origin in SOURCE_ORIGINS:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path not in {"", "/"}:
            raise RuntimeError("DOCUMENT_SOURCE_ORIGINS entries must be exact HTTP(S) origins")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise RuntimeError("DOCUMENT_SOURCE_ORIGINS entries must not contain credentials, path, query, or fragment")
        if ENVIRONMENT == "production" and parsed.scheme != "https":
            raise RuntimeError("DOCUMENT_SOURCE_ORIGINS must use HTTPS in production")


def validate_source_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("document source URL is not allowed")
    origin = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port is not None:
        origin += f":{parsed.port}"
    if SOURCE_ORIGINS and origin.rstrip("/") not in SOURCE_ORIGINS:
        raise ValueError("document source origin is not allowed")


@app.exception_handler(PermissionError)
async def permission_error_handler(_, __):
    return JSONResponse(status_code=401, content={"error": {"code": "worker_authentication", "message": "Worker authentication failed."}})


def resource_limits():
    if os.name == "nt":
        return None

    def apply() -> None:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024 * 1024, 100 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
        resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))

    return apply


async def download(client: httpx.AsyncClient, url: str, destination: Path) -> str:
    digest = hashlib.sha256()
    size = 0
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        declared = response.headers.get("content-length")
        if declared and int(declared) > MAX_DOWNLOAD_BYTES:
            raise ValueError("document download exceeded size limit")
        with destination.open("wb") as handle:
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise ValueError("document download exceeded size limit")
                digest.update(chunk)
                handle.write(chunk)
    return digest.hexdigest()


async def upload_outputs(client: httpx.AsyncClient, base: str, job_id: str, output: Path) -> list[dict]:
    files: list[dict] = []
    candidates = [path for path in sorted(output.iterdir()) if path.is_file()]
    if len(candidates) > MAX_OUTPUT_FILES or sum(path.stat().st_size for path in candidates) > MAX_OUTPUT_BYTES:
        raise ValueError("document worker output exceeded quota")
    for path in candidates:
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        url_response = await client.post(
            f"{base}/api/internal/document-jobs/{job_id}/upload-url",
            headers=worker_headers(),
            json={"name": path.name, "content_type": content_type},
        )
        url_response.raise_for_status()
        target = url_response.json()["data"]["url"]
        put = await client.put(target, content=data, headers={"Content-Type": content_type})
        put.raise_for_status()
        files.append({
            "name": path.name,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "content_type": content_type,
        })
    return files


@app.get("/health")
async def health():
    return {"status": "ok", "service": "document-worker"}


@app.post("/v1/jobs")
async def run_job(job: JobRequest, x_worker_request_secret: str | None = Header(default=None)):
    require_request_secret(x_worker_request_secret)
    validate_fixed_endpoints()
    claims = verify_job_token(job.token)
    if claims.get("job_id") != job.job_id or claims.get("action") != job.action:
        raise ValueError("signed job does not match request")
    if hashlib.sha256(str(job.source_url).encode()).hexdigest() != claims.get("source_url_sha256"):
        raise ValueError("document source URL does not match signed job")
    validate_source_url(str(job.source_url))
    base = CALLBACK_BASE_URL
    async with httpx.AsyncClient(timeout=30) as client:
        consumed = await client.post(
            f"{base}/api/internal/document-jobs/consume",
            headers=worker_headers(),
            json={"token": job.token},
        )
        consumed.raise_for_status()
        consumed_claims = consumed.json()["data"]
        if consumed_claims["job_id"] != job.job_id or consumed_claims["action"] != job.action:
            raise ValueError("consumed job does not match request")
        work = Path(tempfile.mkdtemp(prefix="careerflow-document-"))
        try:
            source = work / job.source_filename
            source_sha = await download(client, str(job.source_url), source)
            if source_sha != claims["source_sha256"] or source_sha != consumed_claims["source_sha256"]:
                raise ValueError("downloaded document hash does not match signed job")
            output = work / "output"
            clean_env = {
                "PATH": os.environ.get("PATH", ""),
                "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
                "PYTHONIOENCODING": "utf-8",
            }
            process = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-m", "document_worker.runner", job.action, str(source), str(output)],
                env=clean_env,
                capture_output=True,
                text=True,
                timeout=RUNNER_TIMEOUT,
                preexec_fn=resource_limits(),
                cwd=work,
                start_new_session=True,
            )
            if process.returncode:
                raise RuntimeError("document runner rejected the file")
            files = await upload_outputs(client, base, job.job_id, output)
            result_file = output / "worker-result.json"
            import json
            result = json.loads(result_file.read_text(encoding="utf-8"))
            complete = await client.post(
                f"{base}/api/internal/document-jobs/{job.job_id}/complete",
                headers=worker_headers(),
                json={"files": files, "result": result},
            )
            complete.raise_for_status()
            return {"status": "succeeded", "job_id": job.job_id, "result": result, "files": files}
        except Exception as exc:
            await client.post(
                f"{base}/api/internal/document-jobs/{job.job_id}/fail",
                headers=worker_headers(),
                json={"error_code": type(exc).__name__},
            )
            raise
        finally:
            shutil.rmtree(work, ignore_errors=True)
