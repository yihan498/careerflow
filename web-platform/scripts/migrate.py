from __future__ import annotations

import asyncio
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from api.db import apply_migrations


async def main() -> None:
    database_url = os.environ.get("MIGRATION_DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("MIGRATION_DATABASE_URL is required and must use a privileged migration role")
    migration_dir = Path(__file__).resolve().parents[1] / "migrations"
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await apply_migrations(connection, sorted(migration_dir.glob("*.sql")))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
