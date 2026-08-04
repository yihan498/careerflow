from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import asyncpg


def env_value(path: Path, name: str) -> str:
    prefix = f"{name}="
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        if raw.startswith(prefix):
            return raw[len(prefix):].strip().strip('"')
    raise RuntimeError(f"{name} is not configured in the deployment environment file")


async def apply(database_url: str, migration: Path) -> None:
    url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(url)
    try:
        async with connection.transaction():
            await connection.execute(migration.read_text(encoding="utf-8"))
    finally:
        await connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply one reviewed CareerFlow SQL migration.")
    parser.add_argument("migration", type=Path)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    if args.migration.name not in {"001_initial.sql", "002_deletion_jobs.sql"}:
        raise RuntimeError("only reviewed CareerFlow migration files are allowed")
    asyncio.run(apply(env_value(args.env_file, "DATABASE_URL"), args.migration))
    print(f"Applied {args.migration.name} successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
