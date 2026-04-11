from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

QueryMode = Literal[
    "exact_lookup",
    "law_constrained_search",
    "domain_search",
    "broad_search",
]
DetectedDomain = Literal[
    "employment",
    "civil",
    "criminal",
    "tax",
    "administrative",
    "constitutional",
    "corporate",
    "unknown",
]
PlanMode = Literal["exact", "constrained", "broad"]


@dataclass(slots=True)
class DetectedLawRef:
    raw_ref: str
    law_number: str
    year: str
    law_iri: str


@dataclass(slots=True)
class QueryUnderstanding:
    raw_query: str
    cleaned_query: str
    detected_law_refs: list[DetectedLawRef] = field(default_factory=list)
    detected_paragraphs: list[str] = field(default_factory=list)
    detected_domain: DetectedDomain = "unknown"
    query_mode: QueryMode = "broad_search"
    keywords: list[str] = field(default_factory=list)
    normalized_tokens: list[str] = field(default_factory=list)
    domain_confidence: float = 0.0
    # Expanded query for sparse (BM25) retrieval only.
    # Set when the query matches a known topic keyword (výpověď, odstupné, …).
    # Dense retrieval always uses cleaned_query so embedding quality is unaffected.
    expanded_query: str | None = None


@dataclass(slots=True)
class RetrievalBoostFactors:
    law_match_boost: float = 0.30
    paragraph_match_boost: float = 0.32
    preferred_law_boost: float = 0.16
    exact_match_boost: float = 0.42
    structural_neighbor_boost: float = 0.05
    text_overlap_weight: float = 0.28
    law_mismatch_penalty: float = 0.35


@dataclass(slots=True)
class RetrievalPlan:
    target_collections: list[str] = field(default_factory=lambda: ["czech_laws_v2"])
    law_filter: list[str] = field(default_factory=list)
    paragraph_filter: list[str] = field(default_factory=list)
    preferred_law_iris: list[str] = field(default_factory=list)
    candidate_k: int = 80
    use_dense: bool = True
    use_sparse: bool = True
    boost_factors: RetrievalBoostFactors = field(default_factory=RetrievalBoostFactors)
    mode: PlanMode = "broad"
    structural_window: int = 1
    allow_fallback_broadening: bool = True


@dataclass(slots=True)
class CandidateBatch:
    exact_hits: list[dict[str, Any]] = field(default_factory=list)
    dense_hits: list[dict[str, Any]] = field(default_factory=list)
    sparse_hits: list[dict[str, Any]] = field(default_factory=list)
    neighbor_hits: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class EvidencePackItem:
    chunk_id: str
    law_iri: str
    paragraph: str | None
    text: str
    score: float
    source_metadata: dict[str, Any] = field(default_factory=dict)
    validation_flags: dict[str, Any] = field(default_factory=dict)
    chunk_index: int = 0
    source_type: str = "law_fragment"
    source: str | None = None
    dense_score: float = 0.0
    sparse_score: float = 0.0
    rrf_score: float = 0.0


@dataclass(slots=True)
class EvidencePack:
    items: list[EvidencePackItem] = field(default_factory=list)
    understanding: QueryUnderstanding | None = None
    plan: RetrievalPlan | None = None


@dataclass(slots=True)
class ValidationResult:
    evidence_pack: EvidencePack
    should_broaden: bool = False
    reason: str = ""
