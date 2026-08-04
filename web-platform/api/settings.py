from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    app_origin: str = "http://localhost:8000"
    database_url: str = "sqlite+aiosqlite:///./runtime/careerflow-web.sqlite3"
    supabase_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_issuer: str = ""
    supabase_jwks_url: str = ""
    supabase_service_role_key: str = ""
    r2_endpoint_url: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "careerflow-private"
    r2_region: str = "auto"
    credential_master_key: str = "development-only-credential-key-change-me"
    credential_key_version: int = 1
    document_token_secret: str = "development-only-document-token-secret"
    document_worker_shared_secret: str = "development-only-worker-secret"
    document_worker_request_secret: str = "development-only-worker-request-secret"
    document_worker_url: str = "http://localhost:8081"
    document_callback_base_url: str = ""
    turnstile_secret_key: str = ""
    dev_auth_bypass: bool = False
    dev_user_id: str = "00000000-0000-0000-0000-000000000001"
    max_source_file_bytes: int = 10 * 1024 * 1024
    max_user_storage_bytes: int = 50 * 1024 * 1024
    global_storage_capacity_bytes: int = 10 * 1024 * 1024 * 1024
    maintenance_interval_seconds: int = 3600
    credential_ttl_seconds: int = 8 * 60 * 60
    model_timeout_seconds: int = 180
    document_timeout_seconds: int = 240
    cors_origins: list[str] = Field(default_factory=list)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    def validate_production(self) -> None:
        if not self.is_production:
            return
        forbidden = ("development-only", "replace-with")
        secrets = (
            self.credential_master_key,
            self.document_token_secret,
            self.document_worker_shared_secret,
            self.document_worker_request_secret,
        )
        if any(any(marker in value for marker in forbidden) for value in secrets):
            raise RuntimeError("production secrets are not configured")
        if self.dev_auth_bypass:
            raise RuntimeError("DEV_AUTH_BYPASS cannot be enabled in production")
        if not self.supabase_jwks_url:
            raise RuntimeError("SUPABASE_JWKS_URL is required in production")
        if not self.supabase_url:
            raise RuntimeError("SUPABASE_URL is required in production")
        if not self.supabase_service_role_key:
            raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required in production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings
