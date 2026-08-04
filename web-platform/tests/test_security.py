import base64

import jwt
import pytest

from api.security import CredentialCipher, DocumentTokenSigner, EncryptedSecret


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
    token, _ = signer.issue("job-1", "inspect", "a" * 64)
    claims = signer.verify(token)
    assert claims.job_id == "job-1"
    with pytest.raises(jwt.InvalidTokenError):
        signer.verify(token[:-2] + "xx")

