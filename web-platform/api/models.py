from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uuid_str() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class CandidateProfileRow(Base):
    __tablename__ = "candidate_profiles"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    source_artifact_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ResumeTemplateRow(Base):
    __tablename__ = "resume_templates"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    template_id: Mapped[str] = mapped_column(String(64), default="default")
    source_object_key: Mapped[str] = mapped_column(String(1000))
    profile_object_key: Mapped[str] = mapped_column(String(1000))
    source_sha256: Mapped[str] = mapped_column(String(64))
    source_filename: Mapped[str] = mapped_column(String(300))
    document_format: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "template_id", name="uq_user_template"),)


class ApplicationRow(Base):
    __tablename__ = "applications"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    company: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(300))
    jd: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(32), default="created")
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    draft_bundle: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    document_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    active_output_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (Index("ix_applications_user_updated", "user_id", "updated_at"),)


class ApprovalRow(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    bundle_hash: Mapped[str] = mapped_column(String(64))
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    application_id: Mapped[str | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(64))
    version_id: Mapped[str] = mapped_column(String(64), default=uuid_str)
    object_key: Mapped[str] = mapped_column(String(1000), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderCredentialRow(Base):
    __tablename__ = "provider_credentials"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    provider: Mapped[str] = mapped_column(String(32))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    key_version: Mapped[int] = mapped_column(Integer)
    key_last_four: Mapped[str] = mapped_column(String(8))
    base_url: Mapped[str] = mapped_column(String(1000))
    model: Mapped[str] = mapped_column(String(300))
    persistent: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "session_id", "provider", name="uq_credential_scope"),)


class AgentRunRow(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    application_id: Mapped[str | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=True)
    run_type: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    idempotency_key: Mapped[str] = mapped_column(String(128))
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_run_idempotency"),)


class DocumentJobRow(Base):
    __tablename__ = "document_jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    application_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    source_sha256: Mapped[str] = mapped_column(String(64))
    token_jti: Mapped[str] = mapped_column(String(64), unique=True)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    output_prefix: Mapped[str] = mapped_column(String(1000))
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewRow(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), unique=True)
    outcome: Mapped[str] = mapped_column(String(32))
    raw_feedback: Mapped[dict[str, Any]] = mapped_column(JSON)
    category: Mapped[str] = mapped_column(String(64))
    coaching: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
