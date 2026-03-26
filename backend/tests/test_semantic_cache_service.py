from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.cache.schemas import SemanticCacheEntry, SemanticCacheMatch
from app.modules.common.cache.semantic_cache import SemanticCacheService
from app.modules.common.observability.cache_metrics import CacheMetricsService
from app.modules.common.querying.schemas import QueryContext, QueryType
from app.modules.common.reasoning.schemas import ConfidenceDecision, ConfidenceLevel
from app.modules.common.responses.schemas import CitationAnswer, ResponseProvenance, SearchAnswerResponse
from app.modules.common.qdrant.schemas import CollectionEmbeddingMetadata


class FakeSemanticRedisClient:
    def __init__(self) -> None:
        self.matches: list[SemanticCacheMatch] = []
        self.index_calls = 0
        self.upsert_calls = 0

    def ensure_semantic_index(self, index_name: str, prefix: str, vector_dim: int) -> bool:
        self.index_calls += 1
        return True

    def search_semantic_entries(self, index_name: str, key_context, query_vector: list[float], top_k: int):
        return self.matches

    def upsert_semantic_entry(self, index_name: str, entry_key: str, entry, query_vector: list[float], ttl_seconds):
        self.upsert_calls += 1
        self.matches = [SemanticCacheMatch(entry=entry, distance=0.02, similarity=0.98)]
        return True


class FakeVectorStore:
    alias_name = "legal_documents_active"

    def get_active_collection_name(self) -> str:
        return "legal_documents__hash__abc__v1"

    def get_active_collection_metadata(self) -> CollectionEmbeddingMetadata:
        return CollectionEmbeddingMetadata(
            embedding_provider="hash",
            embedding_model="deterministic-hash-384",
            embedding_dim=3,
            embedding_revision="deterministic_hash_v2",
            embedding_fingerprint="abc123",
        )


class FakeEmbeddingService:
    class Profile:
        fingerprint = "abc123"

    profile = Profile()

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


def build_query_context(query_type: QueryType = QueryType.EXACT_STATUTE) -> QueryContext:
    return QueryContext(
        raw_query="§ 655 občanský zákoník",
        normalized_query="§ 655 občanský zákoník",
        query_hash="query-hash",
        query_type=query_type,
        domain=DomainEnum.LAW,
        jurisdiction=CountryEnum.CZECHIA,
        citation_patterns=["§ 655"],
        keyword_terms=["obcansky", "zakonik"],
        expects_deterministic_answer=True,
    )


def build_response(use_llm: bool = False) -> SearchAnswerResponse:
    return SearchAnswerResponse(
        query_context=build_query_context(),
        decision=ConfidenceDecision(
            level=ConfidenceLevel.HIGH if not use_llm else ConfidenceLevel.MEDIUM,
            use_llm=use_llm,
            response_type="citation_answer" if not use_llm else "semantic_explanation",
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
                llm_used=use_llm,
                retrieval_mode="hybrid",
                reason_codes=["citation_match"],
            ),
            sources=[],
        ),
        results=[],
    )


def build_service(client=None, threshold: float = 0.93) -> SemanticCacheService:
    return SemanticCacheService(
        client=client or FakeSemanticRedisClient(),
        vector_store=FakeVectorStore(),
        embedding_service=FakeEmbeddingService(),
        enabled=True,
        ttl_seconds=7200,
        response_schema_version="v1",
        strategy_prompt_version="v1",
        similarity_threshold=threshold,
        search_limit=3,
        metrics_service=CacheMetricsService(),
    )


def test_semantic_cache_service_round_trips_deterministic_response():
    client = FakeSemanticRedisClient()
    service = build_service(client=client)
    query_context = build_query_context()
    response = build_response(use_llm=False)

    service.set(query_context, response)
    cached = service.get(query_context)

    assert cached is not None
    assert cached.response.answer_type == "citation_answer"
    assert client.index_calls >= 1
    assert client.upsert_calls == 1
    metrics = service.metrics_service.snapshot()
    assert metrics.semantic_cache.writes == 1
    assert metrics.semantic_cache.hits == 1


def test_semantic_cache_service_skips_llm_responses():
    client = FakeSemanticRedisClient()
    service = build_service(client=client)

    service.set(build_query_context(), build_response(use_llm=True))

    assert client.upsert_calls == 0
    assert service.metrics_service.snapshot().semantic_cache.skipped == 1


def test_semantic_cache_service_respects_similarity_threshold():
    client = FakeSemanticRedisClient()
    service = build_service(client=client, threshold=0.99)
    query_context = build_query_context()
    response = build_response(use_llm=False)

    service.set(query_context, response)
    cached = service.get(query_context)

    assert cached is None
    assert service.metrics_service.snapshot().semantic_cache.misses == 1
