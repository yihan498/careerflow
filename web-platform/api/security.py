from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from shared.contracts import DocumentTokenClaims


def _key_bytes(configured: str, production: bool) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(configured + "=" * (-len(configured) % 4))
    except ValueError:
        decoded = b""
    if len(decoded) == 32:
        return decoded
    if production:
        raise RuntimeError("CREDENTIAL_MASTER_KEY must be a base64-encoded 32-byte key")
    return hashlib.sha256(configured.encode("utf-8")).digest()


@dataclass(frozen=True)
class EncryptedSecret:
    ciphertext: bytes
    nonce: bytes
    key_version: int


class CredentialCipher:
    def __init__(self, configured_key: str, key_version: int, production: bool):
        self._aes = AESGCM(_key_bytes(configured_key, production))
        self.key_version = key_version

    def encrypt(self, plaintext: str, user_id: str, provider: str) -> EncryptedSecret:
        nonce = secrets.token_bytes(12)
        aad = f"careerflow:{user_id}:{provider}:v{self.key_version}".encode()
        ciphertext = self._aes.encrypt(nonce, plaintext.encode(), aad)
        return EncryptedSecret(ciphertext, nonce, self.key_version)

    def decrypt(self, encrypted: EncryptedSecret, user_id: str, provider: str) -> str:
        if encrypted.key_version != self.key_version:
            raise ValueError("credential key version is not available")
        aad = f"careerflow:{user_id}:{provider}:v{encrypted.key_version}".encode()
        return self._aes.decrypt(encrypted.nonce, encrypted.ciphertext, aad).decode()


class DocumentTokenSigner:
    def __init__(self, secret: str):
        if len(secret) < 32:
            raise RuntimeError("DOCUMENT_TOKEN_SECRET must contain at least 32 characters")
        self.secret = secret

    def issue(self, job_id: str, action: str, source_sha256: str, ttl_seconds: int = 300) -> tuple[str, str]:
        jti = secrets.token_urlsafe(24)
        payload = {
            "jti": jti,
            "job_id": job_id,
            "action": action,
            "source_sha256": source_sha256,
            "exp": int(time.time()) + ttl_seconds,
            "iat": int(time.time()),
            "aud": "careerflow-document-worker",
        }
        return jwt.encode(payload, self.secret, algorithm="HS256"), jti

    def verify(self, token: str) -> DocumentTokenClaims:
        payload = jwt.decode(token, self.secret, algorithms=["HS256"], audience="careerflow-document-worker")
        return DocumentTokenClaims.model_validate(payload)

