from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.qdrant.schemas import HybridSearchResponse, RetrievalFeatureSet, SearchResultItem
from app.modules.czechia.retrieval.labor_evidence_gate import LaborEvidenceGate
from app.modules.czechia.retrieval.labor_gate import LaborGateDecision


def _result(text: str, *, score: float = 0.95, document_id: str = "local:sb/2006/262") -> SearchResultItem:
    return SearchResultItem(
        chunk_id=f"chunk:{abs(hash(text))}",
        document_id=document_id,
        filename="Sb_262_2006.txt",
        country=CountryEnum.CZECHIA,
        domain=DomainEnum.LAW,
        jurisdiction_module="czechia",
        text=text,
        chunk_index=0,
        source_type="legal_collection_json",
        source="Sb_262_2006",
        case_id=None,
        tags=["law"],
        score=score,
    )


def _gate_decision() -> LaborGateDecision:
    return LaborGateDecision(
        bucket="labor_in_domain",
        message="",
        reason_codes=["employment_domain_signal"],
        explicit_labor_law=False,
    )


def test_labor_evidence_gate_passes_exact_paragraph_hit() -> None:
    retrieval = HybridSearchResponse(
        results=[
            _result("§ 52 Zaměstnavatel může dát zaměstnanci výpověď jen z těchto důvodů:"),
        ],
        features=RetrievalFeatureSet(
            top_dense_score=0.95,
            top_fused_score=0.95,
            score_gap=0.10,
            keyword_coverage=0.9,
            phrase_match=True,
            citation_match=True,
            domain_consistency=1.0,
            supporting_chunks=1,
        ),
    )

    decision = LaborEvidenceGate().evaluate(
        query="§ 52 zákoník práce",
        gate_decision=_gate_decision(),
        retrieval=retrieval,
    )

    assert decision.status == "pass"
    assert "exact_paragraph_hit" in decision.reason_codes


def test_labor_evidence_gate_blocks_weak_topic_evidence() -> None:
    retrieval = HybridSearchResponse(
        results=[_result("DOVOLENÁ")],
        features=RetrievalFeatureSet(
            top_dense_score=0.92,
            top_fused_score=0.92,
            score_gap=0.04,
            keyword_coverage=0.05,
            phrase_match=False,
            citation_match=False,
            domain_consistency=1.0,
            supporting_chunks=0,
        ),
    )

    decision = LaborEvidenceGate().evaluate(
        query="mám nárok na odstupné při nadbytečnosti",
        gate_decision=_gate_decision(),
        retrieval=retrieval,
    )

    assert decision.status == "weak_evidence"
    assert "no_substantive_labor_chunks" in decision.reason_codes


def test_labor_evidence_gate_passes_natural_language_labor_query_with_anchor_hits() -> None:
    retrieval = HybridSearchResponse(
        results=[
            _result("§ 67 Při rozvázání pracovního poměru výpovědí danou zaměstnavatelem z důvodů uvedených v § 52 náleží zaměstnanci odstupné."),
            _result("§ 52 Zaměstnavatel může dát zaměstnanci výpověď jen z těchto důvodů:"),
        ],
        features=RetrievalFeatureSet(
            top_dense_score=0.89,
            top_fused_score=0.89,
            score_gap=0.06,
            keyword_coverage=0.52,
            phrase_match=False,
            citation_match=False,
            domain_consistency=1.0,
            supporting_chunks=2,
        ),
    )

    decision = LaborEvidenceGate().evaluate(
        query="mám nárok na odstupné při výpovědi pro nadbytečnost",
        gate_decision=_gate_decision(),
        retrieval=retrieval,
    )

    assert decision.status == "pass"
    assert decision.metrics["anchor_hits"] >= 1

