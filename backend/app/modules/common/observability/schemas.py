from datetime import datetime

from pydantic import BaseModel, Field


class CounterBucket(BaseModel):
    hits: int = 0
    misses: int = 0
    writes: int = 0
    write_failures: int = 0
    disabled: int = 0
    skipped: int = 0
    unsupported: int = 0
    errors: int = 0


class PipelineCounters(BaseModel):
    requests_total: int = 0
    retrieval_executions: int = 0
    llm_executions: int = 0
    strategy_executions: int = 0


class CacheMetricsSnapshot(BaseModel):
    started_at: datetime
    exact_cache: CounterBucket = Field(default_factory=CounterBucket)
    semantic_cache: CounterBucket = Field(default_factory=CounterBucket)
    pipeline: PipelineCounters = Field(default_factory=PipelineCounters)


class CacheRuntimeStatus(BaseModel):
    redis_enabled: bool
    redis_reachable: bool
    exact_cache_enabled: bool
    semantic_cache_enabled: bool
    semantic_search_supported: bool | None = None
    active_collection: str | None = None
    embedding_fingerprint: str | None = None
