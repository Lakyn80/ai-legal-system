from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.prompts.search_answers import is_substantive
from app.modules.common.qdrant.lexical_reranker import LexicalReranker
from app.modules.common.qdrant.schemas import HybridSearchResponse, SearchResultItem
from app.modules.common.querying.schemas import QueryContext
from app.modules.czechia.retrieval.labor_gate import LABOR_LAW_IRI, LaborGateDecision
from app.modules.czechia.retrieval.text_utils import extract_paragraphs_from_text, normalize_text

WEAK_EVIDENCE_FALLBACK = (
    "Nemám dost přesný právní podklad v zákoníku práce pro spolehlivou odpověď. "
    "Upřesněte prosím dotaz nebo uveďte konkrétní ustanovení."
)

LaborEvidenceStatus = Literal["pass", "weak_evidence", "block"]

_LABOR_TOPIC_ANCHORS: list[tuple[str, set[str]]] = [
    ("vypovedni doba", {"51"}),
    ("okamzite zruseni", {"55", "56", "57"}),
    ("zkusebni doba", {"35", "66"}),
    ("odstupne", {"67", "68", "73a"}),
    ("nadbytecn", {"52", "67"}),
    ("vypoved", {"50", "52", "53", "54", "55", "56", "57"}),
    ("dovolena", {"211", "212", "213", "214", "215", "216", "217", "218", "222", "223"}),
    ("pracovni smlouva", {"33", "34", "35", "36", "37", "38", "39"}),
    ("prestav", {"88"}),
    ("mzda", {"109", "113", "141", "142", "144"}),
]


@dataclass(slots=True)
class LaborEvidenceDecision:
    status: LaborEvidenceStatus
    message: str
    reason_codes: list[str] = field(default_factory=list)
    metrics: dict[str, float | int | bool] = field(default_factory=dict)

    @property
    def allows_llm(self) -> bool:
        return self.status == "pass"

    def to_search_result(self) -> SearchResultItem:
        return SearchResultItem(
            chunk_id=f"labor_evidence:{self.status}",
            document_id="",
            filename="Nedostatečný právní podklad",
            country=CountryEnum.CZECHIA,
            domain=DomainEnum.LAW,
            jurisdiction_module="czechia",
            text=self.message,
            chunk_index=0,
            source_type="system_fallback",
            source="labor_evidence_gate",
            case_id=None,
            tags=["labor_evidence_gate", self.status],
            score=1.0,
        )


class LaborEvidenceGate:
    """Hard pre-LLM evidence gate for the labor-only vertical."""

    def __init__(self, reranker: LexicalReranker | None = None) -> None:
        self._reranker = reranker or LexicalReranker()

    def evaluate(
        self,
        *,
        query: str,
        gate_decision: LaborGateDecision,
        retrieval: HybridSearchResponse,
        query_context: QueryContext | None = None,
    ) -> LaborEvidenceDecision:
        if not gate_decision.allows_retrieval:
            return LaborEvidenceDecision(
                status="block",
                message=gate_decision.message,
                reason_codes=["pre_retrieval_gate_blocked"],
                metrics={},
            )

        results = retrieval.results or []
        if not results:
            return LaborEvidenceDecision(
                status="weak_evidence",
                message=WEAK_EVIDENCE_FALLBACK,
                reason_codes=["no_results"],
                metrics={"result_count": 0},
            )

        if results[0].chunk_id.startswith("labor_gate:"):
            return LaborEvidenceDecision(
                status="block",
                message=results[0].text,
                reason_codes=["system_gate_result"],
                metrics={"result_count": len(results)},
            )

        labor_results = [result for result in results[:5] if result.document_id == LABOR_LAW_IRI]
        top_law_match = bool(results and results[0].document_id == LABOR_LAW_IRI)
        substantive_count = sum(1 for result in labor_results if is_substantive(result.text or ""))
        lexical_overlaps = [
            float(self._reranker.score_result(query, result)["overlap_ratio"])
            for result in labor_results
        ]
        max_overlap = max(lexical_overlaps, default=0.0)
        requested_paragraphs = set(extract_paragraphs_from_text(query))
        anchor_hits = self._count_anchor_hits(query=query, results=labor_results)
        supporting_chunks = retrieval.features.supporting_chunks
        metrics = {
            "result_count": len(results),
            "labor_result_count": len(labor_results),
            "top_law_match": top_law_match,
            "substantive_count": substantive_count,
            "max_overlap": round(max_overlap, 4),
            "anchor_hits": anchor_hits,
            "supporting_chunks": supporting_chunks,
        }

        if requested_paragraphs:
            exact_hit = any(
                requested_paragraphs.intersection(extract_paragraphs_from_text(result.text or ""))
                for result in labor_results
            )
            if top_law_match and exact_hit:
                return LaborEvidenceDecision(
                    status="pass",
                    message="",
                    reason_codes=["exact_paragraph_hit"],
                    metrics=metrics,
                )
            return LaborEvidenceDecision(
                status="weak_evidence",
                message=WEAK_EVIDENCE_FALLBACK,
                reason_codes=["exact_paragraph_miss"],
                metrics=metrics,
            )

        if not top_law_match or not labor_results:
            return LaborEvidenceDecision(
                status="weak_evidence",
                message=WEAK_EVIDENCE_FALLBACK,
                reason_codes=["missing_labor_anchor"],
                metrics=metrics,
            )

        if substantive_count == 0:
            return LaborEvidenceDecision(
                status="weak_evidence",
                message=WEAK_EVIDENCE_FALLBACK,
                reason_codes=["no_substantive_labor_chunks"],
                metrics=metrics,
            )

        if anchor_hits == 0 and max_overlap < 0.18 and supporting_chunks < 1:
            return LaborEvidenceDecision(
                status="weak_evidence",
                message=WEAK_EVIDENCE_FALLBACK,
                reason_codes=["low_overlap_without_anchor"],
                metrics=metrics,
            )

        return LaborEvidenceDecision(
            status="pass",
            message="",
            reason_codes=["labor_evidence_pass"],
            metrics=metrics,
        )

    def _count_anchor_hits(self, *, query: str, results: list[SearchResultItem]) -> int:
        normalized_query = normalize_text(query)
        expected_anchor_set = set()
        for trigger, anchors in _LABOR_TOPIC_ANCHORS:
            if trigger in normalized_query:
                expected_anchor_set.update(anchors)
        if not expected_anchor_set:
            return 0
        hits = 0
        for result in results:
            if expected_anchor_set.intersection(extract_paragraphs_from_text(result.text or "")):
                hits += 1
        return hits
