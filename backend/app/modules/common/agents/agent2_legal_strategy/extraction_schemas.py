"""
Structured output for Agent 2 legal extraction mode.

This schema is used when Agent 2 operates as a document classification
and legal extraction layer rather than a pure strategy builder.

Design principles:
- Documents are NEVER truncated or summarized destructively
- Every document gets a stable, deterministic ID
- Every issue maps to provisions from the evidence pack only
- Every defense block references its parent issue by ID
- The output is flat-serializable to JSON and Redis-ready

Schema version: agent2_legal_extraction.v1
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Legal basis reference (points into the evidence pack)
# ---------------------------------------------------------------------------

class LegalBasisRef(BaseModel):
    """Reference to a provision from the supplied evidence pack."""

    law: str = Field(
        ...,
        description="Short law label matching the evidence pack, e.g. ГПК РФ, СК РФ, ЕКПЧ.",
    )
    provision: str = Field(
        ...,
        description="Article/provision number, e.g. '113', '407', '6'.",
    )
    why_applicable: str = Field(
        default="",
        description="Explanation of why this provision applies to the issue.",
    )
    legal_effect: str = Field(
        default="",
        description="The legal consequence of applying this provision to the established facts.",
    )


class EvidenceRef(BaseModel):
    """Traceable reference to exact source text used in issue/defense output."""

    doc_id: str = Field(..., description="Stable document ID, e.g. case::<case_id>::doc::<id>.")
    page: int = Field(..., ge=1, description="Page number inside the referenced document.")
    quote: str = Field(..., description="Exact Russian quote from source text (no translation, no paraphrase).")


# ---------------------------------------------------------------------------
# Document item — single case document, no destructive summarization
# ---------------------------------------------------------------------------

class DocumentItem(BaseModel):
    """
    Single case document within a group.

    IMPORTANT: This item must preserve full document identity.
    The summary field is supplementary — it is NOT a replacement for
    the full document. Full text is accessed via full_text_reference.
    """

    doc_id: str = Field(
        ...,
        description="Stable ID: case::<case_id>::doc::<logical_index_or_primary_doc_id>",
    )
    logical_index: int = Field(
        ...,
        ge=0,
        description="Sequential 0-based index within this group.",
    )
    primary_document_id: str = Field(
        default="",
        description="Source document ID from the upstream storage/ingestion system.",
    )
    document_type: str = Field(
        ...,
        description=(
            "Type of document: judgment | appeal | claim | party_submission | order | "
            "evidence | procedural_document | translation | service_document | other_relevant_document"
        ),
    )
    document_date: str = Field(
        default="",
        description="ISO date or partial date, e.g. 2024-03-15 or 2024-03.",
    )
    document_role: str = Field(
        default="",
        description="Role of the issuing party: plaintiff | defendant | court | expert | other.",
    )
    title: str = Field(
        default="",
        description="Document title or short identifying description.",
    )
    is_core_document: bool = Field(
        default=True,
        description="True for judgments, appeals, claims. False for auxiliary attachments.",
    )
    source_pages: list[str] = Field(
        default_factory=list,
        description="Page references from the source document, e.g. ['p.3', 'p.7-9'].",
    )
    full_text_reference: str = Field(
        default="",
        description=(
            "Reference path or ID to the full document text in the storage layer. "
            "Used to retrieve the complete text without bloating this JSON record."
        ),
    )
    summary: str = Field(
        default="",
        description=(
            "Short factual summary of the document content. "
            "MUST preserve core legal claims, dates, and procedural context. "
            "NOT a replacement for the full text — this is a navigation aid only."
        ),
    )
    key_points: list[str] = Field(
        default_factory=list,
        description="Key legal or factual points extracted from this document.",
    )
    evidence_value: str = Field(
        default="",
        description="What this document proves, supports, or refutes in the case.",
    )
    procedural_value: str = Field(
        default="",
        description="Procedural significance: basis for appeal, deadline evidence, etc.",
    )


# ---------------------------------------------------------------------------
# Document group — typed collection of related documents
# ---------------------------------------------------------------------------

class DocumentGroup(BaseModel):
    """
    Typed group of case documents.

    group_name must be one of:
        judgments | appeals | claims | party_submissions | orders |
        evidence | procedural_documents | translations | service_documents |
        other_relevant_documents
    """

    group_id: str = Field(
        ...,
        description="Stable ID: case::<case_id>::group::<group_name>",
    )
    group_name: str = Field(
        ...,
        description="Type of documents in this group (snake_case, see above).",
    )
    documents: list[DocumentItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Issue item — extracted legal issue with mapping to evidence pack
# ---------------------------------------------------------------------------

class IssueItem(BaseModel):
    """
    Single legal issue extracted from the case documents.

    issue_slug must be a stable snake_case identifier, e.g.:
        service_abroad | no_interpreter | missed_deadline | alimony_obligation
    """

    issue_id: str = Field(
        ...,
        description="Stable ID: case::<case_id>::issue::<issue_slug>",
    )
    issue_slug: str = Field(
        ...,
        description="URL-safe snake_case slug, e.g. service_abroad, no_interpreter.",
    )
    issue_title: str = Field(
        ...,
        description="Human-readable issue title, e.g. 'Service of process to foreign address'.",
    )
    factual_basis: list[str] = Field(
        default_factory=list,
        description="Facts from the case that establish this issue.",
    )
    supporting_doc_ids: list[str] = Field(
        default_factory=list,
        description="doc_id references to documents that support this issue.",
    )
    court_or_opponent_position: str = Field(
        default="",
        description="The opposing party's or court's stated position on this issue.",
    )
    problem_description: str = Field(
        default="",
        description="Detailed description of the legal problem: what went wrong and why it matters.",
    )
    defense_argument: str = Field(
        default="",
        description="Core defense argument for this issue in plain language.",
    )
    legal_basis: list[LegalBasisRef] = Field(
        default_factory=list,
        description="Applicable law provisions from the evidence pack only.",
    )
    requested_consequence: str = Field(
        default="",
        description="Relief or consequence sought: reversal, restoration of deadline, etc.",
    )
    evidence_gaps: list[str] = Field(
        default_factory=list,
        description="Missing evidence or facts needed to strengthen this issue.",
    )
    evidence_refs: list[EvidenceRef] = Field(
        default_factory=list,
        description="Exact evidence anchors (doc/page/quote) supporting this issue.",
    )
    requires_evidence: bool = Field(
        default=False,
        description="True when no suitable quote-level evidence could be attached.",
    )


# ---------------------------------------------------------------------------
# Defense block — full argument for a single issue
# ---------------------------------------------------------------------------

class DefenseBlock(BaseModel):
    """
    Full defense argument block for a single legal issue.

    argument_markdown must be substantive — not a one-liner.
    It should cover: issue statement, factual basis, legal basis,
    violation, procedural consequence, and relief sought.
    """

    defense_id: str = Field(
        ...,
        description="Stable ID: case::<case_id>::defense::<issue_slug>",
    )
    issue_id: str = Field(
        ...,
        description="References the parent IssueItem.issue_id.",
    )
    title: str = Field(
        default="",
        description="Title of this defense block.",
    )
    argument_markdown: str = Field(
        default="",
        description=(
            "Full defense argument in markdown format. Must cover: "
            "(1) issue statement, (2) factual basis, (3) applicable law from evidence pack, "
            "(4) violation analysis, (5) legal consequence, (6) relief sought. "
            "NOT a one-liner — must provide actionable legal content."
        ),
    )
    supporting_doc_ids: list[str] = Field(
        default_factory=list,
        description="doc_id references to documents supporting this defense argument.",
    )
    legal_basis_refs: list[str] = Field(
        default_factory=list,
        description="Human-readable provision identifiers, e.g. 'ГПК РФ ст.113', 'СК РФ ст.80'.",
    )
    evidence_refs: list[EvidenceRef] = Field(
        default_factory=list,
        description="Exact evidence anchors (doc/page/quote) supporting this defense block.",
    )


# ---------------------------------------------------------------------------
# Top-level extraction output
# ---------------------------------------------------------------------------

class LegalExtractionAgent2Output(BaseModel):
    """
    Full legal extraction output from Agent 2.

    Organizes case documents into typed groups, extracts legal issues
    with stable IDs, and generates defense blocks — all cross-referenced
    and searchable by case_id, group, document, or issue.

    This output is designed to be:
    - JSON-serializable
    - Redis-storable (flat key structure via stable IDs)
    - FE-queryable (by case_id, group_name, issue_slug)
    - PowerShell-searchable (by case_id prefix or group prefix)
    """

    schema_version: str = Field(default="agent2_legal_extraction.v1")
    case_id: str = Field(default="", description="Case identifier from the input payload.")
    source_artifact: str = Field(
        default="",
        description="Optional reference to the source document bundle or upload ID.",
    )
    groups: list[DocumentGroup] = Field(
        default_factory=list,
        description="All case documents classified into typed groups.",
    )
    issues: list[IssueItem] = Field(
        default_factory=list,
        description="Extracted legal issues, each with factual basis and law mapping.",
    )
    defense_blocks: list[DefenseBlock] = Field(
        default_factory=list,
        description="Defense argument blocks, one per issue.",
    )
