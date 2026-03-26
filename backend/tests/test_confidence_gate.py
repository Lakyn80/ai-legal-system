from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.qdrant.schemas import HybridSearchResponse, RetrievalFeatureSet, SearchResultItem
from app.modules.common.querying.schemas import QueryContext, QueryType
from app.modules.common.reasoning.confidence import ConfidenceGate
from app.modules.common.reasoning.schemas import ConfidenceLevel


def build_context(query_type: QueryType) -> QueryContext:
    return QueryContext(
        raw_query="§ 655 občanský zákoník",
        normalized_query="§ 655 občanský zákoník",
        query_hash="hash",
        query_type=query_type,
        domain=DomainEnum.LAW,
        jurisdiction=CountryEnum.CZECHIA,
        citation_patterns=["§ 655"],
        keyword_terms=["obcansky", "zakonik"],
        expects_deterministic_answer=True,
    )


def build_retrieval(
    top_fused_score: float,
    score_gap: float,
    keyword_coverage: float,
    citation_match: bool,
    phrase_match: bool = False,
    supporting_chunks: int = 1,
) -> HybridSearchResponse:
    return HybridSearchResponse(
        results=[
            SearchResultItem(
                chunk_id="chunk-1",
                document_id="doc-1",
                filename="collection.json",
                country=CountryEnum.CZECHIA,
                domain=DomainEnum.LAW,
                jurisdiction_module="czechia",
                text="Občanský zákoník upravuje soukromá práva a povinnosti.",
                chunk_index=0,
                source_type="legal_collection_json",
                source="Sb_2012_89_2026-01-01_IZ",
                tags=["law"],
                score=0.8,
            )
        ],
        features=RetrievalFeatureSet(
            top_dense_score=0.8,
            top_fused_score=top_fused_score,
            score_gap=score_gap,
            keyword_coverage=keyword_coverage,
            phrase_match=phrase_match,
            citation_match=citation_match,
            domain_consistency=1.0,
            supporting_chunks=supporting_chunks,
        ),
    )


def test_confidence_gate_returns_high_for_exact_statute():
    gate = ConfidenceGate()

    decision = gate.evaluate(
        build_context(QueryType.EXACT_STATUTE),
        build_retrieval(0.9, 0.08, 0.66, True),
    )

    assert decision.level == ConfidenceLevel.HIGH
    assert decision.use_llm is False
    assert decision.response_type == "citation_answer"


def test_confidence_gate_returns_medium_for_semantic_law():
    gate = ConfidenceGate()

    decision = gate.evaluate(
        build_context(QueryType.SEMANTIC_LAW),
        build_retrieval(0.6, 0.01, 0.42, False, supporting_chunks=1),
    )

    assert decision.level == ConfidenceLevel.MEDIUM
    assert decision.use_llm is True
    assert decision.response_type == "semantic_explanation"
