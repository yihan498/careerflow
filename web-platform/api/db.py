from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base
from .settings import get_settings


settings = get_settings()
if settings.database_url.startswith("sqlite"):
    Path("runtime").mkdir(exist_ok=True)
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    if settings.is_production:
        migration = Path(__file__).resolve().parents[1] / "migrations" / "002_deletion_jobs.sql"
        async with engine.begin() as connection:
            # This additive migration is idempotent and serialized across serverless cold starts.
            await connection.exec_driver_sql("select pg_advisory_lock(hashtext('careerflow-web-migrations'))")
            try:
                await connection.exec_driver_sql(migration.read_text(encoding="utf-8"))
            finally:
                await connection.exec_driver_sql("select pg_advisory_unlock(hashtext('careerflow-web-migrations'))")
        return
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
