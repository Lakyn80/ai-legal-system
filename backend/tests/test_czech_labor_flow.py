from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.graph.schemas import StrategyResponse, StrategyResult
from app.modules.common.llm.provider import BaseLLMProvider
from app.modules.common.orchestration.search_pipeline import SearchAnswerService
from app.modules.common.qdrant.schemas import HybridSearchResponse, RetrievalFeatureSet, SearchRequest, SearchResultItem
from app.modules.common.querying.service import QueryProcessingService
from app.modules.common.reasoning.confidence import ConfidenceGate
from app.modules.common.responses.builders import SearchResponseBuilder
from app.modules.czechia.retrieval.labor_evidence_gate import LaborEvidenceGate, WEAK_EVIDENCE_FALLBACK
from app.modules.czechia.retrieval.labor_gate import LaborGate, NON_LEGAL_FALLBACK
from app.modules.czechia.retrieval.service import CzechLawRetrievalService
from app.modules.registry import JurisdictionRegistry


class CountingLLMProvider(BaseLLMProvider):
    def __init__(self) -> None:
        self.calls = 0

    def invoke_structured(self, system_prompt: str, user_prompt: str, schema):
        self.calls += 1
        return schema(
            jurisdiction="czechia",
            domain="law",
            query="test",
            summary="llm",
            explanation="llm",
            key_points=[],
            document_ids=[],
            chunk_ids=[],
            confidence=0.64,
            provenance={
                "llm_used": True,
                "retrieval_mode": "hybrid",
                "reason_codes": ["semantic_needs_llm"],
                "model_name": "gpt-4o-mini",
            },
            sources=[],
        )

    def invoke_text(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        return user_prompt


class FakeRetrievalService:
    def __init__(self, response: HybridSearchResponse) -> None:
        self.response = response
        self.calls = 0

    def retrieve(self, request: SearchRequest) -> HybridSearchResponse:
        self.calls += 1
        return self.response


class FakeStrategyEngine:
    def generate(self, request):
        return StrategyResponse(
            strategy=StrategyResult(
                jurisdiction=CountryEnum.CZECHIA,
                domain="mixed",
                summary="Strategie",
                facts=[],
                relevant_laws=[],
                relevant_court_positions=[],
                arguments_for_client=[],
                arguments_against_client=[],
                risks=[],
                recommended_actions=[],
                missing_documents=[],
                confidence=0.64,
            ),
            retrieved_chunks=[],
        )


class DummyEmbeddingService:
    def embed_query(self, text: str) -> list[float]:
        raise AssertionError("Embedding must not be called for blocked queries.")


class DummyDenseRetriever:
    url = "http://unused"
    api_key = None

    def retrieve(self, *args, **kwargs):
        raise AssertionError("Dense retrieval must not run for blocked queries.")

    def exact_lookup(self, *args, **kwargs):
        raise AssertionError("Exact lookup must not run for blocked queries.")


def _search_result(text: str, *, score: float = 0.95) -> SearchResultItem:
    return SearchResultItem(
        chunk_id=f"chunk:{abs(hash(text))}",
        document_id="local:sb/2006/262",
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


def _build_answer_service(retrieval_service: FakeRetrievalService, llm_provider: CountingLLMProvider) -> SearchAnswerService:
    return SearchAnswerService(
        query_processing_service=QueryProcessingService(registry=JurisdictionRegistry()),
        retrieval_service=retrieval_service,
        confidence_gate=ConfidenceGate(),
        response_builder=SearchResponseBuilder(),
        llm_provider=llm_provider,
        strategy_engine=FakeStrategyEngine(),
        llm_model_name="gpt-4o-mini",
        pre_retrieval_gate=LaborGate(),
        pre_llm_evidence_gate=LaborEvidenceGate(),
    )


def test_search_answer_service_blocks_non_legal_before_retrieval_and_llm() -> None:
    retrieval = FakeRetrievalService(HybridSearchResponse())
    llm = CountingLLMProvider()
    service = _build_answer_service(retrieval, llm)

    response = service.answer(
        SearchRequest(
            query="počasí Praha zítra",
            country=CountryEnum.CZECHIA,
            domain=DomainEnum.LAW,
            top_k=3,
        )
    )

    assert retrieval.calls == 0
    assert llm.calls == 0
    assert response.response.summary == NON_LEGAL_FALLBACK
    assert response.decision.use_llm is False


def test_search_answer_service_uses_weak_evidence_fallback_without_llm() -> None:
    retrieval = FakeRetrievalService(
        HybridSearchResponse(
            results=[_search_result("DOVOLENÁ")],
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
    )
    llm = CountingLLMProvider()
    service = _build_answer_service(retrieval, llm)

    response = service.answer(
        SearchRequest(
            query="mám nárok na odstupné při nadbytečnosti",
            country=CountryEnum.CZECHIA,
            domain=DomainEnum.LAW,
            top_k=3,
        )
    )

    assert retrieval.calls == 1
    assert llm.calls == 0
    assert response.response.summary == WEAK_EVIDENCE_FALLBACK
    assert response.decision.use_llm is False


def test_search_answer_service_keeps_exact_labor_lookup_deterministic() -> None:
    retrieval = FakeRetrievalService(
        HybridSearchResponse(
            results=[_search_result("§ 52 Zaměstnavatel může dát zaměstnanci výpověď jen z těchto důvodů:")],
            features=RetrievalFeatureSet(
                top_dense_score=0.95,
                top_fused_score=0.95,
                score_gap=0.10,
                keyword_coverage=0.95,
                phrase_match=True,
                citation_match=True,
                domain_consistency=1.0,
                supporting_chunks=1,
            ),
        )
    )
    llm = CountingLLMProvider()
    service = _build_answer_service(retrieval, llm)

    response = service.answer(
        SearchRequest(
            query="§ 52 zákoník práce",
            country=CountryEnum.CZECHIA,
            domain=DomainEnum.LAW,
            top_k=3,
        )
    )

    assert retrieval.calls == 1
    assert llm.calls == 0
    assert response.response.answer_type == "citation_answer"


def test_czech_law_retrieval_service_blocks_before_planner_execution() -> None:
    service = CzechLawRetrievalService(
        embedding_service=DummyEmbeddingService(),
        dense_retriever=DummyDenseRetriever(),
        labor_gate=LaborGate(),
    )
    service._execute_plan = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("planner must not run"))

    results = service.search(
        SearchRequest(
            query="recept na svíčkovou",
            country=CountryEnum.CZECHIA,
            domain=DomainEnum.LAW,
            top_k=3,
        )
    )

    assert results[0].chunk_id == "labor_gate:non_legal"

