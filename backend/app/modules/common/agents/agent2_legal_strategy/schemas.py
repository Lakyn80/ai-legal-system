"""
Structured output for Agent 2 (legal strategy builder).

Maps to the eight sections in the product prompt. Use with strict LLM JSON mode
or `invoke_structured(..., schema=LegalStrategyAgent2Output)`.

When STRICT RELIABILITY is enabled, populate `insufficient_support_items` instead
of stating unsupported conclusions in narrative fields.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Strength = Literal["strong", "medium", "weak"]


class SourceRef(BaseModel):
    """Reference to a provision from the supplied evidence pack only."""

    law: str = Field(..., description="Short law label as in the pack, e.g. GPK RF, ECHR.")
    article: str = Field(..., description="Article number as string, e.g. 9, 113, 6.")
    title: str | None = Field(default=None, description="Optional heading from the pack.")


class PrimaryBasisItem(BaseModel):
    provision: SourceRef
    why_it_matters: str = Field(
        ...,
        description=(
            "Substantive litigation analysis: FACT → LEGAL RULE (from excerpt) → VIOLATION → CONSEQUENCE. "
            "Minimum several sentences; no generic 'supports the issue' filler."
        ),
    )
    connected_facts: list[str] = Field(
        default_factory=list,
        description="Facts from the input that tie to this provision.",
    )


class SupportingBasisItem(BaseModel):
    provision: SourceRef
    how_it_reinforces: str = Field(
        ...,
        description="2+ sentences: how this norm reinforces the primary line; causal, not generic.",
    )


class FactToLawRow(BaseModel):
    issue_name: str
    relevant_facts: list[str] = Field(default_factory=list)
    legal_provisions: list[SourceRef] = Field(default_factory=list)
    assessment_strength: Strength
    comment: str = Field(
        ...,
        description="Mini-brief: FACT → RULE → VIOLATION → CONSEQUENCE for this issue; multi-sentence.",
    )


class StrategicAssessmentBlock(BaseModel):
    strongest_arguments: list[str] = Field(default_factory=list)
    weaker_arguments: list[str] = Field(default_factory=list)
    likely_vulnerabilities: list[str] = Field(default_factory=list)
    opposing_side_may_argue: list[str] = Field(default_factory=list)


class MissingEvidenceBlock(BaseModel):
    what_is_unclear: list[str] = Field(default_factory=list)
    needed_documents_or_facts: list[str] = Field(default_factory=list)


class NextStepItem(BaseModel):
    step_order: int = Field(..., ge=1, description="1-based sequence.")
    action: str = Field(..., description="Concrete, case-oriented action.")


class InsufficientSupportItem(BaseModel):
    """Use under STRICT RELIABILITY when a point cannot be grounded."""

    topic: str
    reason: str = Field(
        default="Insufficient support in current evidence pack.",
        description="Standard phrase when conclusion cannot be tied to fact + provision.",
    )


class LegalStrategyAgent2Output(BaseModel):
    """
    Full Agent 2 output. All legal citations must appear in the input evidence pack.
    """

    schema_version: str = Field(default="agent2_legal_strategy.v1")
    case_theory: str = Field(
        ...,
        description="Dense multi-paragraph theory of the case; procedural and material threads.",
    )
    primary_legal_basis: list[PrimaryBasisItem] = Field(default_factory=list)
    supporting_legal_basis: list[SupportingBasisItem] = Field(default_factory=list)
    fact_to_law_mapping: list[FactToLawRow] = Field(default_factory=list)
    strategic_assessment: StrategicAssessmentBlock = Field(
        default_factory=StrategicAssessmentBlock,
    )
    missing_evidence_gaps: MissingEvidenceBlock = Field(
        default_factory=MissingEvidenceBlock,
    )
    recommended_next_steps: list[NextStepItem] = Field(default_factory=list)
    draft_argument_direction: str = Field(
        ...,
        description="Full litigation thesis: lead argument, attack vectors, relief; not one sentence.",
    )
    insufficient_support_items: list[InsufficientSupportItem] = Field(
        default_factory=list,
        description=(
            "Optional: conclusions that could not be tied to a supplied fact and provision. "
            "Prefer this over hallucinating under STRICT RELIABILITY."
        ),
    )
