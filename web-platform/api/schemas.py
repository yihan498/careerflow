from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from shared.contracts import CandidateProfile, DocumentPlan, DraftBundle, ProviderId, ReviewInput


class ProviderCredentialInput(BaseModel):
    provider: ProviderId
    api_key: str = Field(min_length=8, max_length=2_000)
    base_url: str = Field(default="", max_length=1_000)
    model: str = Field(default="", max_length=300)
    save: bool = False
    session_id: str = Field(min_length=16, max_length=128)


class ApplicationCreate(BaseModel):
    company: str = Field(min_length=1, max_length=300)
    role: str = Field(min_length=1, max_length=300)
    jd: str = Field(min_length=80, max_length=200_000)


class DraftRequest(BaseModel):
    provider: ProviderId
    session_id: str = Field(min_length=16, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=128)


class DocumentPlanRequest(DraftRequest):
    template_id: str = Field(default="default", pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")


class DraftEdit(BaseModel):
    bundle: DraftBundle
    document_plan: DocumentPlan | None = None


class InterviewRequest(BaseModel):
    provider: ProviderId
    session_id: str = Field(min_length=16, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=128)
    source_urls: list[HttpUrl] = Field(default_factory=list, max_length=30)
    use_native_search: bool = False


class ReviewRequest(BaseModel):
    feedback: ReviewInput
    provider: ProviderId | None = None
    session_id: str | None = None


class ProfileConfirm(BaseModel):
    profile: CandidateProfile


class ProfileExtractRequest(BaseModel):
    resume_text: str = Field(min_length=80, max_length=200_000)
    provider: ProviderId
    session_id: str = Field(min_length=16, max_length=128)
    consent_to_provider: bool
    idempotency_key: str = Field(min_length=8, max_length=128)


class ApiEnvelope(BaseModel):
    data: Any
