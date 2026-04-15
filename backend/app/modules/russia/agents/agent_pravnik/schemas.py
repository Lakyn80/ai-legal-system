"""
Pydantic schemas for agent_pravnik — Russian litigation drafting (see AGENT_PRAVNIK_RU_PLAN.md).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.common.agents.agent2_legal_strategy.input_schemas import LegalEvidencePack
from app.modules.common.agents.agent2_legal_strategy.schemas import LegalStrategyAgent2Output, SourceRef

PRAVNIK_SCHEMA_VERSION = "agent_pravnik_ru.v1"

DocumentKindRuLiteral = Literal[
    "appeal_draft",
    "procedural_motion_restoration",
    "defense_position_memo",
    "lawyer_internal_brief",
]

PravnikWorkModeLiteral = Literal[
    "strict_litigation",
    "structured_defense",
    "lawyer_briefing",
    "client_explanation",
]

EpistemicLabelLiteral = Literal["fact", "allegation", "to_be_proven"]
RiskLevelLiteral = Literal["high", "medium", "low"]
RiskSourceLiteral = Literal["agent2", "input"]


class RequestedRelief(BaseModel):
    """Structured petit / relief block."""

    model_config = ConfigDict(extra="forbid")

    primary_asks: list[str] = Field(default_factory=list)
    alternative_asks: list[str] = Field(default_factory=list)
    non_claim_procedural: list[str] = Field(
        default_factory=list,
        description="Non-claim procedural requests, e.g. deadline restoration.",
    )


class EvidenceRequestItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description_ru: str = Field(..., description="Description in Russian.")
    grounding_reference: str = Field(
        ...,
        description="Link to input fact or gap from missing_evidence / insufficient_support.",
    )
    epistemic_label: EpistemicLabelLiteral = Field(
        ...,
        description="fact | allegation | to_be_proven",
    )


class RiskAssessmentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: RiskLevelLiteral = Field(..., description="Severity.")
    description_ru: str = Field(...)
    mitigation_ru: str = Field(default="", description="How to mitigate or what to prove.")
    source: RiskSourceLiteral = Field(
        default="agent2",
        description="Whether risk stems from agent2 analysis or input-only.",
    )


class GroundingManifest(BaseModel):
    """Machine-checkable list of cited provisions — must subset of evidence pack."""

    model_config = ConfigDict(extra="forbid")

    cited_provisions: list[SourceRef] = Field(default_factory=list)
    flags: list[str] = Field(
        default_factory=list,
        description='e.g. "no_new_articles_added"',
    )
    validation_status: str | None = Field(
        default=None,
        description="Optional human-readable status from validator.",
    )


class ProceduralPostureNotes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes_ru: str = Field(default="")
    deadline_mentions_only_from_input: bool = Field(
        default=True,
        description="True when deadlines were not invented beyond input.",
    )


class AgentPravnikRuInput(BaseModel):
    """Full drafting payload — Agent 2 output + same evidence pack + case bundle."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(..., min_length=1, max_length=256)
    jurisdiction: Literal["Russia"] = Field(
        ...,
        description="Russian branch only; runtime guard.",
    )
    document_kind: DocumentKindRuLiteral = Field(...)
    work_mode: PravnikWorkModeLiteral = Field(...)
    legal_evidence_pack: LegalEvidencePack
    agent2_output: LegalStrategyAgent2Output
    cleaned_summary: str = Field(default="", max_length=50_000)
    facts: list[str] = Field(default_factory=list)
    issue_flags: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    claims_or_questions: list[str] = Field(default_factory=list)
    procedural_posture: str | None = Field(
        default=None,
        description="User-supplied procedural posture only; agent must not invent history.",
    )
    party_labels: dict[str, str] | None = Field(
        default=None,
        description="Optional role labels, e.g. истец / ответчик.",
    )
    court_instance_hint: str | None = Field(
        default=None,
        description="Optional instance hint from user.",
    )


class AgentPravnikRuOutput(BaseModel):
    """Structured litigation draft — narrative fields in Russian."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=PRAVNIK_SCHEMA_VERSION)
    document_kind: DocumentKindRuLiteral
    work_mode: PravnikWorkModeLiteral
    document_title: str = Field(..., description="e.g. Апелляционная жалоба (проект)")
    header_block: str = Field(default="")
    procedural_background: str = Field(default="")
    facts_section: str = Field(default="")
    legal_argument_section: str = Field(default="")
    violation_and_consequence: str = Field(default="")
    requested_relief: RequestedRelief = Field(default_factory=RequestedRelief)
    evidence_requests: list[EvidenceRequestItem] = Field(default_factory=list)
    procedural_motions: list[str] = Field(default_factory=list)
    deadlines_and_posture: ProceduralPostureNotes = Field(default_factory=ProceduralPostureNotes)
    risk_notes: list[RiskAssessmentItem] = Field(default_factory=list)
    grounding_manifest: GroundingManifest = Field(default_factory=GroundingManifest)
    full_document_markdown: str = Field(default="")
    lawyer_brief_ru: str | None = None
    client_explanation_ru: str | None = None
