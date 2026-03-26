from app.modules.common.observability.cache_metrics import CacheMetricsService


def test_cache_metrics_service_tracks_counters():
    service = CacheMetricsService()

    service.increment_requests()
    service.increment_retrieval()
    service.increment_llm()
    service.increment_strategy()
    service.record_exact("hits")
    service.record_exact("writes")
    service.record_semantic("misses")
    service.record_semantic("unsupported")

    snapshot = service.snapshot()

    assert snapshot.pipeline.requests_total == 1
    assert snapshot.pipeline.retrieval_executions == 1
    assert snapshot.pipeline.llm_executions == 1
    assert snapshot.pipeline.strategy_executions == 1
    assert snapshot.exact_cache.hits == 1
    assert snapshot.exact_cache.writes == 1
    assert snapshot.semantic_cache.misses == 1
    assert snapshot.semantic_cache.unsupported == 1


def test_cache_metrics_service_reset_clears_counters():
    service = CacheMetricsService()

    service.increment_requests()
    service.record_exact("hits")

    snapshot = service.reset()

    assert snapshot.pipeline.requests_total == 0
    assert snapshot.exact_cache.hits == 0
