from pathlib import Path
from types import SimpleNamespace

import pytest

import api.db as db
from api.db import apply_migrations, migration_statements


class Result:
    def scalar_one_or_none(self):
        return None


class Connection:
    def __init__(self):
        self.driver_sql: list[str] = []
        self.executed: list[tuple[str, dict[str, str]]] = []

    async def exec_driver_sql(self, statement: str):
        self.driver_sql.append(statement)

    async def execute(self, statement, params):
        self.executed.append((str(statement), params))
        return Result()


def test_migration_statements_are_individually_preparable():
    statements = migration_statements("create table one (id text);\ncreate index two on one(id);\n")
    assert statements == ["create table one (id text)", "create index two on one(id)"]


@pytest.mark.asyncio
async def test_migrations_use_transaction_lock_and_separate_statements(tmp_path: Path):
    migration = tmp_path / "001_test.sql"
    migration.write_text("create table one (id text); create index two on one(id);", encoding="utf-8")
    connection = Connection()

    await apply_migrations(connection, [migration])

    assert connection.driver_sql[0].startswith("select pg_advisory_xact_lock")
    assert "pg_advisory_unlock" not in "\n".join(connection.driver_sql)
    assert "create table one (id text)" in connection.driver_sql
    assert "create index two on one(id)" in connection.driver_sql
    assert connection.executed[-1][1] == {"version": "001_test.sql"}


@pytest.mark.asyncio
async def test_production_startup_uses_runtime_role_for_connectivity_only(monkeypatch):
    connection = Connection()

    class Context:
        async def __aenter__(self):
            return connection

        async def __aexit__(self, *_):
            return None

    class Engine:
        def connect(self):
            return Context()

    monkeypatch.setattr(db, "settings", SimpleNamespace(is_production=True))
    monkeypatch.setattr(db, "engine", Engine())

    await db.init_db()

    assert connection.driver_sql == ["select 1"]
