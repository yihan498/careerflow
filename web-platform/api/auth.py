from __future__ import annotations

from dataclasses import dataclass
import asyncio
from time import monotonic

import httpx
import jwt
from fastapi import Depends, Header

from shared.errors import PlatformError

from .settings import Settings, get_settings


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str


class JwksCache:
    def __init__(self):
        self.payload: dict | None = None
        self.loaded_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self, url: str, force: bool = False) -> dict:
        if not force and self.payload and monotonic() - self.loaded_at < 3600:
            return self.payload
        async with self._lock:
            if not force and self.payload and monotonic() - self.loaded_at < 3600:
                return self.payload
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await client.get(url)
                response.raise_for_status()
            self.payload = response.json()
            self.loaded_at = monotonic()
            return self.payload


jwks_cache = JwksCache()


async def current_user(
    authorization: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if settings.dev_auth_bypass and not settings.is_production:
        return CurrentUser(x_dev_user or settings.dev_user_id, "developer@example.invalid")
    if not authorization or not authorization.startswith("Bearer "):
        raise PlatformError("authentication_required", "Please sign in.", 401)
    token = authorization.removeprefix("Bearer ").strip()
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") not in {"RS256", "ES256"}:
            raise jwt.InvalidAlgorithmError("unsupported JWT algorithm")
        jwks = await jwks_cache.get(settings.supabase_jwks_url)
        matching = next((item for item in jwks.get("keys", []) if item.get("kid") == header.get("kid")), None)
        if matching is None:
            jwks = await jwks_cache.get(settings.supabase_jwks_url, force=True)
            matching = next(item for item in jwks.get("keys", []) if item.get("kid") == header.get("kid"))
        key = jwt.PyJWK.from_dict(matching).key
        issuer = settings.supabase_jwt_issuer or f"{settings.supabase_url.rstrip('/')}/auth/v1"
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256", "ES256"],
            audience=settings.supabase_jwt_audience,
            issuer=issuer,
        )
    except Exception as exc:
        raise PlatformError("invalid_session", "The session is invalid or expired.", 401) from exc
    return CurrentUser(str(claims["sub"]), str(claims.get("email", "")))
