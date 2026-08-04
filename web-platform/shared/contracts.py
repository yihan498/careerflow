from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Stage(str, Enum):
    ONBOARDING = "onboarding"
    CREATED = "created"
    DRAFTED = "drafted"
    APPROVED = "approved"
    BUILT = "built"
    SUBMITTED = "submitted"
    INTERVIEWING = "interviewing"
    CLOSED = "closed"


ALLOWED_TRANSITIONS: dict[Stage, set[Stage]] = {
    Stage.ONBOARDING: {Stage.CREATED},
    Stage.CREATED: {Stage.DRAFTED},
    Stage.DRAFTED: {Stage.DRAFTED, Stage.APPROVED},
    Stage.APPROVED: {Stage.DRAFTED, Stage.BUILT},
    Stage.BUILT: {Stage.SUBMITTED, Stage.INTERVIEWING, Stage.CLOSED},
    Stage.SUBMITTED: {Stage.INTERVIEWING, Stage.CLOSED},
    Stage.INTERVIEWING: {Stage.INTERVIEWING, Stage.CLOSED},
    Stage.CLOSED: {Stage.CLOSED},
}


class ProviderId(str, Enum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    ZHIPU = "zhipu"
    KIMI = "kimi"
    MINIMAX = "minimax"
    DOUBAO = "doubao"


class Capability(str, Enum):
    TEXT = "L1"
    STRUCTURED = "L2"
    TOOLS = "L3"
    WEB_SEARCH = "L4"


class DraftBundle(BaseModel):
    resume_markdown: str = Field(min_length=40, max_length=50_000)
    cover_letter_markdown: str = Field(min_length=40, max_length=50_000)
    evidence_map_markdown: str = Field(min_length=40, max_length=50_000)

    def as_contract_files(self) -> dict[str, str]:
        return {
            "resume.md": self.resume_markdown,
            "cover-letter.md": self.cover_letter_markdown,
            "evidence-map.md": self.evidence_map_markdown,
        }


class EducationItem(BaseModel):
    school: str = Field(min_length=1, max_length=300)
    program: str = Field(default="", max_length=300)
    period: str = Field(default="", max_length=100)
    source_text: str = Field(default="", max_length=2_000)


class ExperienceItem(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    organization: str = Field(min_length=1, max_length=300)
    role: str = Field(min_length=1, max_length=300)
    period: str = Field(default="", max_length=100)
    bullets: list[str] = Field(min_length=1, max_length=30)
    source_text: str = Field(default="", max_length=10_000)


class CandidateProfile(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    headline: str = Field(default="", max_length=500)
    education: list[EducationItem] = Field(default_factory=list, max_length=20)
    experiences: list[ExperienceItem] = Field(default_factory=list, max_length=50)
    skills: list[str] = Field(default_factory=list, max_length=200)
    uncertainties: list[str] = Field(default_factory=list, max_length=100)


class ReviewInput(BaseModel):
    outcome: Literal["rejected", "withdrew", "offer", "pending"]
    actual_questions: list[str] = Field(default_factory=list, max_length=100)
    answers: list[str] = Field(default_factory=list, max_length=100)
    feelings: str = Field(default="", max_length=20_000)
    strengths: str = Field(default="", max_length=20_000)
    improvements: str = Field(default="", max_length=20_000)


class DocumentChange(BaseModel):
    region_id: str = Field(min_length=1, max_length=200)
    old_text: str = Field(max_length=20_000)
    new_text: str = Field(min_length=1, max_length=20_000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)


class DocumentPlan(BaseModel):
    template_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    changes: list[DocumentChange] = Field(min_length=1, max_length=300)

    @field_validator("changes")
    @classmethod
    def unique_regions(cls, changes: list[DocumentChange]) -> list[DocumentChange]:
        ids = [change.region_id for change in changes]
        if len(ids) != len(set(ids)):
            raise ValueError("document changes contain duplicate region IDs")
        return changes


class DocumentTokenClaims(BaseModel):
    jti: str
    job_id: str
    action: Literal["inspect", "build"]
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    exp: int


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NEEDS_ATTENTION = "needs_attention"


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def require_transition(current: Stage, target: Stage) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"invalid stage transition: {current.value} -> {target.value}")
