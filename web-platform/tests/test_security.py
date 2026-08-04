import base64

import jwt
import pytest

from api.security import CredentialCipher, DocumentTokenSigner, EncryptedSecret
from api.settings import Settings


def test_credentials_are_randomized_and_bound_to_user_and_provider():
    key = base64.urlsafe_b64encode(b"x" * 32).decode().rstrip("=")
    cipher = CredentialCipher(key, 1, True)
    first = cipher.encrypt("secret-key", "user-a", "openai")
    second = cipher.encrypt("secret-key", "user-a", "openai")
    assert first.ciphertext != second.ciphertext
    assert cipher.decrypt(first, "user-a", "openai") == "secret-key"
    with pytest.raises(Exception):
        cipher.decrypt(first, "user-b", "openai")


def test_document_token_rejects_tampering():
    signer = DocumentTokenSigner("a-document-token-secret-that-is-long-enough")
    token, _ = signer.issue("job-1", "inspect", "a" * 64, "b" * 64)
    claims = signer.verify(token)
    assert claims.job_id == "job-1"
    with pytest.raises(jwt.InvalidTokenError):
        signer.verify(token[:-2] + "xx")


def test_production_requires_distinct_worker_request_secret():
    settings = Settings(
        environment="production",
        credential_master_key=base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("="),
        document_token_secret="t" * 32,
        document_worker_shared_secret="s" * 32,
        document_worker_request_secret="development-only-worker-request-secret",
        supabase_jwks_url="https://example.supabase.co/auth/v1/.well-known/jwks.json",
        supabase_service_role_key="service-role",
    )
    with pytest.raises(RuntimeError):
        settings.validate_production()
