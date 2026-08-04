from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import ConflictError, PlatformError

from .models import AgentRunRow, DocumentJobRow, TaskLeaseRow


T = TypeVar("T")


async def acquire_task_lease(session: AsyncSession, user_id: str, kind: str, ttl_seconds: int = 600) -> None:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=1)
    model = AgentRunRow if kind == "agent" else DocumentJobRow
    recent = await session.scalar(select(func.count()).select_from(model).where(
        model.user_id == user_id,
        model.created_at >= since,
    ))
    if int(recent or 0) >= 30:
        raise PlatformError("task_rate_limit", "This account reached the hourly task limit. Try again later.", 429)
    await session.execute(delete(TaskLeaseRow).where(
        TaskLeaseRow.user_id == user_id,
        TaskLeaseRow.kind == kind,
        TaskLeaseRow.expires_at <= now,
    ))
    session.add(TaskLeaseRow(user_id=user_id, kind=kind, expires_at=now + timedelta(seconds=ttl_seconds)))
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("task_already_running", f"A {kind} task is already running for this account.") from exc


async def release_task_lease(session: AsyncSession, user_id: str, kind: str) -> None:
    await session.rollback()
    await session.execute(delete(TaskLeaseRow).where(TaskLeaseRow.user_id == user_id, TaskLeaseRow.kind == kind))
    await session.commit()


async def with_task_lease(
    session: AsyncSession,
    user_id: str,
    kind: str,
    operation: Callable[[], Awaitable[T]],
    ttl_seconds: int = 600,
) -> T:
    await acquire_task_lease(session, user_id, kind, ttl_seconds)
    try:
        return await operation()
    finally:
        await release_task_lease(session, user_id, kind)
