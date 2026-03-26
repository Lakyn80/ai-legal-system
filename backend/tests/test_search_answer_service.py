from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.graph.schemas import StrategyResponse, StrategyResult
from app.modules.common.llm.provider import BaseLLMProvider
from app.modules.common.orchestration.search_pipeline import SearchAnswerService
from app.modules.common.qdrant.schemas import HybridSearchResponse, RetrievalFeatureSet, SearchRequest, SearchResultItem
from app.modules.common.querying.service import QueryProcessingService
from app.modules.common.reasoning.confidence import ConfidenceGate
from app.modules.common.responses.builders import SearchResponseBuilder
from app.modules.common.responses.schemas import SemanticExplanation
from app.modules.registry import JurisdictionRegistry


class FakeRetrievalService:
    def __init__(self) -> None:
        self.calls = 0

    def retrieve(self, request: SearchRequest) -> HybridSearchResponse:
        self.calls += 1
        result = SearchResultItem(
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
            score=0.75,
        )
        return HybridSearchResponse(
            results=[result],
            features=RetrievalFeatureSet(
                top_dense_score=0.75,
                top_fused_score=0.86,
                score_gap=0.09,
                keyword_coverage=0.8,
                phrase_match=True,
                citation_match=True,
                domain_consistency=1.0,
                supporting_chunks=1,
            ),
        )


class FakeStrategyEngine:
    def generate(self, request):
        return StrategyResponse(
            strategy=StrategyResult(
                jurisdiction=CountryEnum.CZECHIA,
                domain="mixed",
                summary="Strategie byla odvozena z relevantnich pravnich norem.",
                facts=["Existuje spor o vyporadani SJM."],
                relevant_laws=["Obcansky zakoník"],
                relevant_court_positions=["Nejvyssi soud k proporcionalite naroku."],
                arguments_for_client=["Klient ma prokazatelny prispevek."],
                arguments_against_client=["Protistrana bude namitat disproporci."],
                risks=["Neuplna dukazni situace."],
                recommended_actions=["Doplnit financni podklady."],
                missing_documents=["Vypisy z uctu"],
                confidence=0.64,
            ),
            retrieved_chunks=[],
        )


class FakeLLMProvider(BaseLLMProvider):
    def invoke_structured(self, system_prompt: str, user_prompt: str, schema):
        return schema(
            jurisdiction="czechia",
            domain="law",
            query="Jak se vyklada soukroma prava?",
            summary="Shrnuti evidence.",
            explanation="Vysvetleni zalozene na retrieved chunks.",
            key_points=["Soukroma prava a povinnosti."],
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
        return user_prompt


class FakeExactCacheService:
    def __init__(self, cached_response=None) -> None:
        self.cached_response = cached_response
        self.set_calls = 0

    def get(self, query_context):
        return self.cached_response

    def set(self, query_context, response) -> None:
        self.set_calls += 1


class FakeSemanticCacheService:
    def __init__(self, cached_response=None) -> None:
        self.cached_response = cached_response
        self.set_calls = 0

    def get(self, query_context):
        return self.cached_response

    def set(self, query_context, response) -> None:
        self.set_calls += 1


def build_service(
    llm_provider: BaseLLMProvider | None = None,
    exact_cache_service: FakeExactCacheService | None = None,
    semantic_cache_service: FakeSemanticCacheService | None = None,
) -> SearchAnswerService:
    return SearchAnswerService(
        query_processing_service=QueryProcessingService(registry=JurisdictionRegistry()),
        retrieval_service=FakeRetrievalService(),
        confidence_gate=ConfidenceGate(),
        response_builder=SearchResponseBuilder(),
        llm_provider=llm_provider or FakeLLMProvider(),
        strategy_engine=FakeStrategyEngine(),
        llm_model_name="gpt-4o-mini",
        exact_cache_service=exact_cache_service,
        semantic_cache_service=semantic_cache_service,
    )


def test_search_answer_service_returns_citation_answer_for_exact_statute():
    service = build_service()

    response = service.answer(SearchRequest(query="§ 655 občanský zákoník", top_k=3))

    assert response.decision.use_llm is False
    assert response.response.answer_type == "citation_answer"
    assert response.response.chunk_ids == ["chunk-1"]


def test_search_answer_service_routes_strategy_queries_to_strategy_engine():
    service = build_service()

    response = service.answer(
        SearchRequest(
            query="Navrhni strategii sporu o vyporadani SJM",
            country=CountryEnum.CZECHIA,
            top_k=4,
        )
    )

    assert response.response.answer_type == "strategy_answer"
    assert response.decision.use_llm is True


def test_search_answer_service_uses_llm_for_medium_confidence_semantic_query():
    service = build_service(llm_provider=FakeLLMProvider())
    service.retrieval_service = type(
        "MediumRetrievalService",
        (),
        {
            "retrieve": lambda self, request: HybridSearchResponse(
                results=[
                    SearchResultItem(
                        chunk_id="chunk-2",
                        document_id="doc-2",
                        filename="law.txt",
                        country=CountryEnum.CZECHIA,
                        domain=DomainEnum.LAW,
                        jurisdiction_module="czechia",
                        text="Tento zakon upravuje vlastnicka prava a povinnosti.",
                        chunk_index=0,
                        source_type="txt",
                        source="manual",
                        tags=["law"],
                        score=0.62,
                    )
                ],
                features=RetrievalFeatureSet(
                    top_dense_score=0.62,
                    top_fused_score=0.6,
                    score_gap=0.01,
                    keyword_coverage=0.4,
                    phrase_match=False,
                    citation_match=False,
                    domain_consistency=1.0,
                    supporting_chunks=1,
                ),
            )
        },
    )()

    response = service.answer(SearchRequest(query="Jak se vyklada soukroma prava?", top_k=3))

    assert response.response.answer_type == "semantic_explanation"
    assert isinstance(response.response, SemanticExplanation)
    assert response.response.provenance.llm_used is True


def test_search_answer_service_short_circuits_from_exact_cache():
    cached_response = SearchAnswerService(
        query_processing_service=QueryProcessingService(registry=JurisdictionRegistry()),
        retrieval_service=FakeRetrievalService(),
        confidence_gate=ConfidenceGate(),
        response_builder=SearchResponseBuilder(),
        llm_provider=FakeLLMProvider(),
        strategy_engine=FakeStrategyEngine(),
        llm_model_name="gpt-4o-mini",
    ).answer(SearchRequest(query="§ 655 občanský zákoník", top_k=3))

    fake_cache = FakeExactCacheService(cached_response=cached_response)
    service = build_service(exact_cache_service=fake_cache)

    response = service.answer(SearchRequest(query="§ 655 občanský zákoník", top_k=3))

    assert response.response.answer_type == "citation_answer"
    assert fake_cache.set_calls == 0
    assert service.retrieval_service.calls == 0


def test_search_answer_service_short_circuits_from_semantic_cache():
    cached_response = SearchAnswerService(
        query_processing_service=QueryProcessingService(registry=JurisdictionRegistry()),
        retrieval_service=FakeRetrievalService(),
        confidence_gate=ConfidenceGate(),
        response_builder=SearchResponseBuilder(),
        llm_provider=FakeLLMProvider(),
        strategy_engine=FakeStrategyEngine(),
        llm_model_name="gpt-4o-mini",
    ).answer(SearchRequest(query="§ 655 občanský zákoník", top_k=3))

    fake_semantic_cache = FakeSemanticCacheService(cached_response=cached_response)
    service = build_service(
        exact_cache_service=FakeExactCacheService(cached_response=None),
        semantic_cache_service=fake_semantic_cache,
    )

    response = service.answer(SearchRequest(query="§ 655 občanský zákoník", top_k=3))

    assert response.response.answer_type == "citation_answer"
    assert fake_semantic_cache.set_calls == 0
    assert service.retrieval_service.calls == 0
