"""
Typed input contract for Agent 2 — jurisdiction-agnostic.

Populated upstream by retrieval / issue detection (Agent 1). Agent 2 must not fetch law.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.modules.common.agents.agent2_legal_strategy.schemas import SourceRef


class CaseDocumentInput(BaseModel):
    """
    A single case document supplied by the client for legal extraction.

    Examples: court judgment, filed appeal, original claim, party submission,
    expert opinion, service record, notarized translation, court order.

    The content field holds the full text. full_text_reference points to
    external storage when the full text is not inlined.
    """

    model_config = ConfigDict(extra="forbid")

    primary_document_id: str = Field(
        default="",
        description="Upstream document ID (from storage/ingestion layer) for stable referencing.",
    )
    document_type: str = Field(
        default="other_relevant_document",
        description=(
            "Type: judgment | appeal | claim | party_submission | order | "
            "evidence | procedural_document | translation | service_document | other_relevant_document"
        ),
    )
    document_date: str = Field(default="", description="ISO date or partial date, e.g. 2024-03-15.")
    document_role: str = Field(
        default="",
        description="Role of the issuing party: plaintiff | defendant | court | expert | other.",
    )
    title: str = Field(default="", description="Document title or short identifying description.")
    content: str = Field(
        default="",
        description=(
            "Full text of the document. Preserved without truncation. "
            "If too large to inline, use full_text_reference instead."
        ),
        max_length=200_000,
    )
    source_pages: list[str] = Field(
        default_factory=list,
        description="Page references, e.g. ['p.3', 'p.7-9'].",
    )
    full_text_reference: str = Field(
        default="",
        description="Path or ID to the full document in the storage layer.",
    )


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
    case_documents: list[CaseDocumentInput] = Field(
        default_factory=list,
        description=(
            "Case documents supplied by the client for legal extraction: "
            "judgments, appeals, claims, submissions, evidence, service records, etc. "
            "When non-empty, Agent 2 operates in extraction mode (agent2_legal_extraction.v1). "
            "When empty, Agent 2 operates in strategy mode (agent2_legal_strategy.v1)."
        ),
    )
