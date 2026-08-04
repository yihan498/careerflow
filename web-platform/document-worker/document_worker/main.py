from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field, HttpUrl


class JobRequest(BaseModel):
    token: str = Field(min_length=40, max_length=4_000)
    job_id: str = Field(min_length=1, max_length=100)
    action: Literal["inspect", "build"]
    source_url: HttpUrl
    source_filename: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,199}$")
    callback_base_url: HttpUrl


app = FastAPI(title="CareerFlow Isolated Document Worker", docs_url=None, redoc_url=None)
WORKER_SECRET = os.environ.get("DOCUMENT_WORKER_SHARED_SECRET", "")
MAX_DOWNLOAD_BYTES = int(os.environ.get("MAX_DOCUMENT_DOWNLOAD_BYTES", str(24 * 1024 * 1024)))
RUNNER_TIMEOUT = int(os.environ.get("DOCUMENT_RUNNER_TIMEOUT_SECONDS", "180"))


def worker_headers() -> dict[str, str]:
    if len(WORKER_SECRET) < 16:
        raise RuntimeError("DOCUMENT_WORKER_SHARED_SECRET is not configured")
    return {"X-Worker-Secret": WORKER_SECRET}


def resource_limits():
    if os.name == "nt":
        return None

    def apply() -> None:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024 * 1024, 100 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))

    return apply


async def download(client: httpx.AsyncClient, url: str, destination: Path) -> str:
    digest = hashlib.sha256()
    size = 0
    async with client.stream("GET", url) as response:
        response.raise_for_status()
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
    for path in sorted(output.iterdir()):
        if not path.is_file():
            continue
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
async def run_job(job: JobRequest):
    base = str(job.callback_base_url).rstrip("/")
    async with httpx.AsyncClient(timeout=30) as client:
        consumed = await client.post(
            f"{base}/api/internal/document-jobs/consume",
            headers=worker_headers(),
            json={"token": job.token},
        )
        consumed.raise_for_status()
        claims = consumed.json()["data"]
        if claims["job_id"] != job.job_id or claims["action"] != job.action:
            raise ValueError("consumed job does not match request")
        work = Path(tempfile.mkdtemp(prefix="careerflow-document-"))
        try:
            source = work / job.source_filename
            source_sha = await download(client, str(job.source_url), source)
            if source_sha != claims["source_sha256"]:
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
