from datetime import UTC, datetime
from threading import Lock

from app.modules.common.observability.schemas import CacheMetricsSnapshot


class CacheMetricsService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshot = CacheMetricsSnapshot(started_at=datetime.now(tz=UTC))

    def record_exact(self, event: str) -> None:
        with self._lock:
            self._increment_bucket(self._snapshot.exact_cache, event)

    def record_semantic(self, event: str) -> None:
        with self._lock:
            self._increment_bucket(self._snapshot.semantic_cache, event)

    def increment_requests(self) -> None:
        with self._lock:
            self._snapshot.pipeline.requests_total += 1

    def increment_retrieval(self) -> None:
        with self._lock:
            self._snapshot.pipeline.retrieval_executions += 1

    def increment_llm(self) -> None:
        with self._lock:
            self._snapshot.pipeline.llm_executions += 1

    def increment_strategy(self) -> None:
        with self._lock:
            self._snapshot.pipeline.strategy_executions += 1

    def snapshot(self) -> CacheMetricsSnapshot:
        with self._lock:
            return self._snapshot.model_copy(deep=True)

    def reset(self) -> CacheMetricsSnapshot:
        with self._lock:
            self._snapshot = CacheMetricsSnapshot(started_at=datetime.now(tz=UTC))
            return self._snapshot.model_copy(deep=True)

    @staticmethod
    def _increment_bucket(bucket, event: str) -> None:
        if hasattr(bucket, event):
            setattr(bucket, event, getattr(bucket, event) + 1)
