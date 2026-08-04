from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base
from .settings import get_settings


settings = get_settings()
if settings.database_url.startswith("sqlite"):
    Path("runtime").mkdir(exist_ok=True)
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


def migration_statements(script: str) -> list[str]:
    """Split the project's plain-SQL migrations for asyncpg prepared execution."""
    return [statement.strip() for statement in script.split(";") if statement.strip()]


async def apply_migrations(connection: AsyncConnection, migrations: list[Path]) -> None:
    # A transaction-scoped lock is released automatically on commit or rollback.
    # This avoids trying to unlock an already-aborted transaction after a DDL error.
    await connection.exec_driver_sql("select pg_advisory_xact_lock(hashtext('careerflow-web-migrations'))")
    await connection.exec_driver_sql(
        "create table if not exists public.schema_migrations ("
        "version text primary key, applied_at timestamptz not null default now())"
    )
    await connection.exec_driver_sql("alter table public.schema_migrations enable row level security")
    await connection.exec_driver_sql("revoke all on table public.schema_migrations from anon, authenticated")
    for migration in migrations:
        applied = await connection.execute(
            text("select 1 from public.schema_migrations where version = :version"),
            {"version": migration.name},
        )
        if applied.scalar_one_or_none():
            continue
        for statement in migration_statements(migration.read_text(encoding="utf-8")):
            await connection.exec_driver_sql(statement)
        await connection.execute(
            text("insert into public.schema_migrations (version) values (:version)"),
            {"version": migration.name},
        )


async def init_db() -> None:
    if settings.is_production:
        migration_dir = Path(__file__).resolve().parents[1] / "migrations"
        async with engine.begin() as connection:
            await apply_migrations(connection, sorted(migration_dir.glob("*.sql")))
        return
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
