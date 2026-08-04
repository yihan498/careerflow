from __future__ import annotations

import sys
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient


WORKER_ROOT = Path(__file__).resolve().parents[1] / "document-worker"
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from document_worker import main as worker  # noqa: E402


def test_worker_rejects_missing_or_incorrect_request_secret(monkeypatch):
    monkeypatch.setattr(worker, "WORKER_REQUEST_SECRET", "r" * 32)
    with pytest.raises(PermissionError):
        worker.require_request_secret(None)
    with pytest.raises(PermissionError):
        worker.require_request_secret("wrong")
    worker.require_request_secret("r" * 32)


def test_worker_only_accepts_exact_configured_source_origin(monkeypatch):
    monkeypatch.setattr(worker, "SOURCE_ORIGINS", {"https://private.example.com"})
    worker.validate_source_url("https://private.example.com/object?signature=value")
    with pytest.raises(ValueError):
        worker.validate_source_url("https://private.example.com.attacker.test/object")
    with pytest.raises(ValueError):
        worker.validate_source_url("https://private.example.com:444/object")
    with pytest.raises(ValueError):
        worker.validate_source_url("http://127.0.0.1/latest/meta-data")


def test_worker_verifies_job_token_locally(monkeypatch):
    secret = "t" * 32
    monkeypatch.setattr(worker, "DOCUMENT_TOKEN_SECRET", secret)
    token = jwt.encode(
        {
            "job_id": "job-1",
            "action": "inspect",
            "source_sha256": "a" * 64,
            "source_url_sha256": "b" * 64,
            "aud": "careerflow-document-worker",
        },
        secret,
        algorithm="HS256",
    )
    assert worker.verify_job_token(token)["job_id"] == "job-1"
    with pytest.raises(jwt.InvalidTokenError):
        worker.verify_job_token(token[:-2] + "xx")


def test_public_worker_job_route_rejects_unauthenticated_requests(monkeypatch):
    monkeypatch.setattr(worker, "WORKER_REQUEST_SECRET", "r" * 32)
    response = TestClient(worker.app).post("/v1/jobs", json={
        "token": "x" * 40,
        "job_id": "job-1",
        "action": "inspect",
        "source_url": "https://private.example.com/object",
        "source_filename": "source.pdf",
    })
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "worker_authentication"


def test_worker_request_contract_does_not_accept_caller_controlled_callback():
    with pytest.raises(Exception):
        worker.JobRequest.model_validate({
            "token": "x" * 40,
            "job_id": "job-1",
            "action": "inspect",
            "source_url": "https://private.example.com/object",
            "source_filename": "source.pdf",
            "callback_base_url": "https://attacker.example/callback",
        })
