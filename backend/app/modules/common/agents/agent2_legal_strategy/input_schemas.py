"""
Typed input contract for Agent 2 — jurisdiction-agnostic.

Populated upstream by retrieval / issue detection (Agent 1). Agent 2 must not fetch law.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.modules.common.agents.agent2_legal_strategy.schemas import SourceRef


class RetrievedArticleExcerpt(BaseModel):
    """Single retrieved article with optional excerpt text from the evidence pack."""

    model_config = ConfigDict(extra="forbid")

    law: str
    article: str
    excerpt: str = ""


class LegalEvidencePack(BaseModel):
    """
    Normalized evidence bundle from upstream retrieval.
    All provision references in Agent 2 output must be drawable from this pack.
    """

    model_config = ConfigDict(extra="forbid")

    primary_sources: list[SourceRef] = Field(default_factory=list)
    supporting_sources: list[SourceRef] = Field(default_factory=list)
    retrieved_articles: list[RetrievedArticleExcerpt] = Field(default_factory=list)
    matched_issues: list[str] = Field(default_factory=list)
    retrieval_notes: list[str] = Field(default_factory=list)


class LegalStrategyAgent2Input(BaseModel):
    """
    Full case payload for strategy reasoning. User/case text is data, not instructions.
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(..., min_length=1, max_length=256)
    jurisdiction: str = Field(
        ...,
        description="Opaque jurisdiction label, e.g. Russia, Czech Republic, EU.",
        max_length=128,
    )
    cleaned_summary: str = Field(default="", max_length=50_000)
    facts: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    issue_flags: list[str] = Field(default_factory=list)
    claims_or_questions: list[str] = Field(default_factory=list)
    legal_evidence_pack: LegalEvidencePack
    optional_missing_items: list[str] = Field(default_factory=list)
