from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.contracts import ProviderId
from shared.errors import NotFoundError

from .models import ProviderCredentialRow
from .security import CredentialCipher, EncryptedSecret
from .settings import Settings


class CredentialService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cipher = CredentialCipher(
            settings.credential_master_key, settings.credential_key_version, settings.is_production
        )

    async def save(
        self,
        session: AsyncSession,
        user_id: str,
        session_id: str,
        provider: ProviderId,
        api_key: str,
        base_url: str,
        model: str,
        persistent: bool,
    ) -> ProviderCredentialRow:
        await session.execute(
            delete(ProviderCredentialRow).where(
                ProviderCredentialRow.user_id == user_id,
                ProviderCredentialRow.provider == provider.value,
                or_(
                    ProviderCredentialRow.persistent.is_(persistent),
                    ProviderCredentialRow.session_id == session_id,
                ),
            )
        )
        encrypted = self.cipher.encrypt(api_key, user_id, provider.value)
        row = ProviderCredentialRow(
            user_id=user_id,
            session_id=None if persistent else session_id,
            provider=provider.value,
            ciphertext=encrypted.ciphertext,
            nonce=encrypted.nonce,
            key_version=encrypted.key_version,
            key_last_four=api_key[-4:],
            base_url=base_url,
            model=model,
            persistent=persistent,
            expires_at=None if persistent else datetime.now(timezone.utc) + timedelta(seconds=self.settings.credential_ttl_seconds),
        )
        session.add(row)
        await session.flush()
        return row

    async def resolve(
        self, session: AsyncSession, user_id: str, session_id: str, provider: ProviderId
    ) -> tuple[str, ProviderCredentialRow]:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(ProviderCredentialRow)
            .where(
                ProviderCredentialRow.user_id == user_id,
                ProviderCredentialRow.provider == provider.value,
                or_(
                    ProviderCredentialRow.persistent.is_(True),
                    ProviderCredentialRow.session_id == session_id,
                ),
                or_(ProviderCredentialRow.expires_at.is_(None), ProviderCredentialRow.expires_at > now),
            )
            .order_by(ProviderCredentialRow.persistent.asc(), ProviderCredentialRow.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise NotFoundError("No active API credential is configured for this provider.")
        plaintext = self.cipher.decrypt(
            EncryptedSecret(row.ciphertext, row.nonce, row.key_version), user_id, provider.value
        )
        return plaintext, row

    async def delete(self, session: AsyncSession, user_id: str, provider: ProviderId) -> None:
        await session.execute(
            delete(ProviderCredentialRow).where(
                ProviderCredentialRow.user_id == user_id,
                ProviderCredentialRow.provider == provider.value,
            )
        )

