from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.dependencies import (
    get_app_settings,
    get_cache_admin_service,
    get_cache_metrics_service,
    get_czech_search_answer_service,
    get_qdrant_vector_store,
    get_redis_cache_client,
    get_search_answer_service,
)
from app.core.enums import CountryEnum, DomainEnum
from app.main import app
from app.modules.common.cache.admin_service import CacheResetResult
from app.modules.common.observability.cache_metrics import CacheMetricsService
from app.modules.common.querying.schemas import QueryContext, QueryType
from app.modules.common.reasoning.schemas import ConfidenceDecision, ConfidenceLevel
from app.modules.common.responses.schemas import CitationAnswer, ResponseProvenance, SearchAnswerResponse


class FakeCollectionMetadata:
    embedding_fingerprint = "hash-384"


class FakeVectorStore:
    def health_check(self) -> bool:
        return True

    def get_active_collection_metadata(self):
        return FakeCollectionMetadata()

    def get_active_collection_name(self) -> str:
        return "legal_documents_active"


class FakeRedisClient:
    def ping(self) -> bool:
        return True

    def semantic_search_supported(self) -> bool:
        return True


class FakeCacheAdminService:
    def reset(self) -> CacheResetResult:
        return CacheResetResult(exact_entries_deleted=2, semantic_entries_deleted=3)


class FakeSearchAnswerService:
    def answer(self, request):
        return SearchAnswerResponse(
            query_context=QueryContext(
                raw_query=request.query,
                normalized_query=request.query.lower(),
                query_hash="query-hash-1",
                query_type=QueryType.EXACT_STATUTE,
                domain=DomainEnum.LAW,
                jurisdiction=CountryEnum.CZECHIA,
                citation_patterns=["§ 3080"],
                keyword_terms=["občanský", "zákoník"],
                expects_deterministic_answer=True,
            ),
            decision=ConfidenceDecision(
                level=ConfidenceLevel.HIGH,
                use_llm=False,
                response_type="citation_answer",
                reason_codes=["exact_citation_match"],
                score_summary={"top_fused_score": 0.97},
            ),
            response=CitationAnswer(
                jurisdiction="czechia",
                domain="law",
                query=request.query,
                answer="§ 3080 občanského zákoníku byl nalezen.",
                citations=["§ 3080 občanský zákoník"],
                document_ids=["doc-1"],
                chunk_ids=["chunk-1"],
                confidence=0.97,
                provenance=ResponseProvenance(
                    llm_used=False,
                    retrieval_mode="hybrid",
                    reason_codes=["exact_citation_match"],
                    model_name=None,
                ),
                sources=[],
            ),
            results=[],
        )


def test_health_route_returns_runtime_and_metrics():
    metrics_service = CacheMetricsService()
    metrics_service.increment_requests()
    startup_handlers = list(app.router.on_startup)
    app.router.on_startup.clear()
    app.dependency_overrides[get_app_settings] = lambda: Settings(
        app_env="test",
        redis_enabled=True,
        exact_cache_enabled=True,
        semantic_cache_enabled=True,
    )
    app.dependency_overrides[get_cache_metrics_service] = lambda: metrics_service
    app.dependency_overrides[get_qdrant_vector_store] = lambda: FakeVectorStore()
    app.dependency_overrides[get_redis_cache_client] = lambda: FakeRedisClient()

    try:
        with TestClient(app) as client:
            response = client.get("/api/health")
    finally:
        app.dependency_overrides.clear()
        app.router.on_startup[:] = startup_handlers

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["environment"] == "test"
    assert payload["cache"]["redis_reachable"] is True
    assert payload["cache"]["semantic_search_supported"] is True
    assert payload["metrics"]["pipeline"]["requests_total"] == 1


def test_admin_cache_metrics_route_returns_snapshot():
    metrics_service = CacheMetricsService()
    metrics_service.record_exact("hits")
    startup_handlers = list(app.router.on_startup)
    app.router.on_startup.clear()
    app.dependency_overrides[get_app_settings] = lambda: Settings(
        redis_enabled=True,
        exact_cache_enabled=True,
        semantic_cache_enabled=True,
    )
    app.dependency_overrides[get_cache_metrics_service] = lambda: metrics_service
    app.dependency_overrides[get_qdrant_vector_store] = lambda: FakeVectorStore()
    app.dependency_overrides[get_redis_cache_client] = lambda: FakeRedisClient()

    try:
        with TestClient(app) as client:
            response = client.get("/api/admin/cache/metrics")
    finally:
        app.dependency_overrides.clear()
        app.router.on_startup[:] = startup_handlers

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime"]["exact_cache_enabled"] is True
    assert payload["metrics"]["exact_cache"]["hits"] == 1


def test_admin_cache_reset_route_returns_deleted_counts():
    startup_handlers = list(app.router.on_startup)
    app.router.on_startup.clear()
    app.dependency_overrides[get_app_settings] = lambda: Settings(redis_enabled=True)
    app.dependency_overrides[get_cache_admin_service] = lambda: FakeCacheAdminService()
    app.dependency_overrides[get_qdrant_vector_store] = lambda: FakeVectorStore()
    app.dependency_overrides[get_redis_cache_client] = lambda: FakeRedisClient()

    try:
        with TestClient(app) as client:
            response = client.post("/api/admin/cache/reset")
    finally:
        app.dependency_overrides.clear()
        app.router.on_startup[:] = startup_handlers

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["cleared"]["exact_entries_deleted"] == 2
    assert payload["cleared"]["semantic_entries_deleted"] == 3


def test_admin_cache_metrics_reset_route_resets_counters():
    metrics_service = CacheMetricsService()
    metrics_service.increment_requests()
    metrics_service.record_semantic("writes")
    startup_handlers = list(app.router.on_startup)
    app.router.on_startup.clear()
    app.dependency_overrides[get_cache_metrics_service] = lambda: metrics_service

    try:
        with TestClient(app) as client:
            response = client.post("/api/admin/cache/metrics/reset")
    finally:
        app.dependency_overrides.clear()
        app.router.on_startup[:] = startup_handlers

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["metrics"]["pipeline"]["requests_total"] == 0
    assert payload["metrics"]["semantic_cache"]["writes"] == 0


def test_search_answer_route_returns_structured_answer():
    startup_handlers = list(app.router.on_startup)
    app.router.on_startup.clear()
    fake = FakeSearchAnswerService()
    app.dependency_overrides[get_search_answer_service] = lambda: fake
    app.dependency_overrides[get_czech_search_answer_service] = lambda: fake

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/search/answer",
                json={
                    "query": "§ 3080 občanský zákoník",
                    "country": "czechia",
                    "domain": "law",
                    "top_k": 3,
                },
            )
    finally:
        app.dependency_overrides.clear()
        app.router.on_startup[:] = startup_handlers

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"]["answer_type"] == "citation_answer"
    assert payload["decision"]["use_llm"] is False
    assert payload["query_context"]["query_type"] == "exact_statute"
