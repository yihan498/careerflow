from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from .db import SessionFactory
from .models import ArtifactRow, DocumentJobRow, ProviderCredentialRow
from .settings import Settings
from .storage import ObjectStore


async def maintenance_once(store: ObjectStore | None) -> None:
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        await session.execute(
            delete(ProviderCredentialRow).where(
                ProviderCredentialRow.persistent.is_(False),
                ProviderCredentialRow.expires_at < now,
            )
        )
        await session.execute(
            delete(DocumentJobRow).where(
                DocumentJobRow.expires_at < now - timedelta(days=1),
                DocumentJobRow.status.in_(["queued", "failed"]),
            )
        )
        stale = list((await session.execute(
            select(ArtifactRow).where(
                ArtifactRow.active.is_(False),
                ArtifactRow.created_at < now - timedelta(days=1),
            ).limit(200)
        )).scalars())
        if store:
            for artifact in stale:
                await store.delete(artifact.object_key)
        for artifact in stale:
            await session.delete(artifact)
        await session.commit()


async def maintenance_loop(settings: Settings, store: ObjectStore | None) -> None:
    while True:
        try:
            await maintenance_once(store)
        except Exception:
            # Operational monitoring captures the exception in production; cleanup must never stop the API.
            pass
        await asyncio.sleep(settings.maintenance_interval_seconds)

