from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.cache.exact_cache import ExactCacheService
from app.modules.common.cache.schemas import ExactCacheEntry
from app.modules.common.observability.cache_metrics import CacheMetricsService
from app.modules.common.querying.schemas import QueryContext, QueryType
from app.modules.common.responses.schemas import CitationAnswer, ResponseProvenance, SearchAnswerResponse
from app.modules.common.reasoning.schemas import ConfidenceDecision, ConfidenceLevel
from app.modules.common.qdrant.schemas import CollectionEmbeddingMetadata


class InMemoryCacheClient:
    def __init__(self) -> None:
        self.storage: dict[str, dict] = {}

    def get_json(self, key: str) -> dict | None:
        return self.storage.get(key)

    def set_json(self, key: str, payload: dict, ttl_seconds: int | None = None) -> bool:
        self.storage[key] = payload
        return True


class FakeVectorStore:
    alias_name = "legal_documents_active"

    def __init__(self, active_collection: str, fingerprint: str) -> None:
        self.active_collection = active_collection
        self.fingerprint = fingerprint

    def get_active_collection_name(self) -> str:
        return self.active_collection

    def get_active_collection_metadata(self) -> CollectionEmbeddingMetadata:
        return CollectionEmbeddingMetadata(
            embedding_provider="hash",
            embedding_model="deterministic-hash-384",
            embedding_dim=384,
            embedding_revision="deterministic_hash_v2",
            embedding_fingerprint=self.fingerprint,
        )


class FakeEmbeddingService:
    class Profile:
        fingerprint = "fallback-fingerprint"

    profile = Profile()


def build_query_context(domain: DomainEnum = DomainEnum.LAW) -> QueryContext:
    return QueryContext(
        raw_query="§ 655 občanský zákoník",
        normalized_query="§ 655 občanský zákoník",
        query_hash="query-hash",
        query_type=QueryType.EXACT_STATUTE,
        domain=domain,
        jurisdiction=CountryEnum.CZECHIA,
        citation_patterns=["§ 655"],
        keyword_terms=["obcansky", "zakonik"],
        expects_deterministic_answer=True,
    )


def build_response() -> SearchAnswerResponse:
    return SearchAnswerResponse(
        query_context=build_query_context(),
        decision=ConfidenceDecision(
            level=ConfidenceLevel.HIGH,
            use_llm=False,
            response_type="citation_answer",
            reason_codes=["citation_match"],
            score_summary={"top_fused_score": 0.91},
        ),
        response=CitationAnswer(
            jurisdiction="czechia",
            domain="law",
            query="§ 655 občanský zákoník",
            answer="Ustanovení upravuje manželské soužití.",
            citations=["collection.json"],
            document_ids=["doc-1"],
            chunk_ids=["chunk-1"],
            confidence=0.88,
            provenance=ResponseProvenance(
                llm_used=False,
                retrieval_mode="hybrid",
                reason_codes=["citation_match"],
            ),
            sources=[],
        ),
        results=[],
    )


def build_service(active_collection: str = "legal_documents__hash__abc__v1") -> ExactCacheService:
    return ExactCacheService(
        client=InMemoryCacheClient(),
        vector_store=FakeVectorStore(active_collection=active_collection, fingerprint="abc123"),
        embedding_service=FakeEmbeddingService(),
        enabled=True,
        ttl_seconds=3600,
        response_schema_version="v1",
        strategy_prompt_version="v1",
        metrics_service=CacheMetricsService(),
    )


def test_exact_cache_service_uses_corpus_aware_key():
    service_a = build_service(active_collection="collection-a")
    service_b = build_service(active_collection="collection-b")

    key_a = service_a.build_cache_key(build_query_context())
    key_b = service_b.build_cache_key(build_query_context())

    assert key_a != key_b


def test_exact_cache_service_round_trips_response():
    service = build_service()
    query_context = build_query_context()
    response = build_response()

    service.set(query_context, response)
    cached = service.get(query_context)

    assert cached is not None
    assert cached.response.answer_type == "citation_answer"
    assert cached.response.chunk_ids == ["chunk-1"]
    metrics = service.metrics_service.snapshot()
    assert metrics.exact_cache.writes == 1
    assert metrics.exact_cache.hits == 1
