from datetime import UTC, datetime, timedelta
import logging

from app.modules.common.cache.client import RedisCacheClient
from app.modules.common.cache.identity import CacheIdentityBuilder
from app.modules.common.cache.schemas import ExactCacheEntry, ExactCacheKeyContext
from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.common.observability.cache_metrics import CacheMetricsService
from app.modules.common.observability.logging import log_event
from app.modules.common.qdrant.client import QdrantVectorStore
from app.modules.common.querying.schemas import QueryContext
from app.modules.common.responses.schemas import SearchAnswerResponse


logger = logging.getLogger(__name__)


class ExactCacheService:
    def __init__(
        self,
        client: RedisCacheClient | None,
        vector_store: QdrantVectorStore,
        embedding_service: EmbeddingService,
        enabled: bool,
        ttl_seconds: int,
        response_schema_version: str,
        strategy_prompt_version: str,
        metrics_service: CacheMetricsService | None = None,
    ) -> None:
        self.client = client
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.enabled = enabled and client is not None
        self.ttl_seconds = ttl_seconds
        self.response_schema_version = response_schema_version
        self.strategy_prompt_version = strategy_prompt_version
        self.metrics_service = metrics_service
        self.identity_builder = CacheIdentityBuilder(
            vector_store=vector_store,
            embedding_service=embedding_service,
            response_schema_version=response_schema_version,
            strategy_prompt_version=strategy_prompt_version,
        )

    def get(self, query_context: QueryContext) -> SearchAnswerResponse | None:
        if not self.enabled or self.client is None:
            self._record("disabled")
            self._log("cache.exact.disabled", query_context=query_context)
            return None
        cache_key = self.build_cache_key(query_context)
        payload = self.client.get_json(cache_key)
        if payload is None:
            self._record("misses")
            self._log("cache.exact.miss", query_context=query_context, cache_key=cache_key)
            return None
        entry = ExactCacheEntry.model_validate(payload)
        self._record("hits")
        self._log("cache.exact.hit", query_context=query_context, cache_key=cache_key)
        return SearchAnswerResponse.model_validate(entry.response_payload)

    def set(self, query_context: QueryContext, response: SearchAnswerResponse) -> None:
        if not self.enabled or self.client is None:
            self._record("disabled")
            self._log("cache.exact.disabled", query_context=query_context)
            return
        cache_key, key_context = self.build_cache_identity(query_context)
        created_at = datetime.now(tz=UTC)
        expires_at = created_at + timedelta(seconds=self.ttl_seconds) if self.ttl_seconds > 0 else None
        payload = response.response
        entry = ExactCacheEntry(
            cache_key=cache_key,
            jurisdiction=key_context.jurisdiction,
            domain=key_context.domain,
            query_type=key_context.query_type,
            active_collection=key_context.active_collection,
            corpus_fingerprint=key_context.corpus_fingerprint,
            embedding_fingerprint=key_context.embedding_fingerprint,
            response_schema_version=key_context.response_schema_version,
            prompt_version=key_context.prompt_version,
            document_ids=getattr(payload, "document_ids", []),
            chunk_ids=getattr(payload, "chunk_ids", []),
            response_payload=response.model_dump(mode="json"),
            created_at=created_at,
            expires_at=expires_at,
        )
        ttl_seconds = self.ttl_seconds if self.ttl_seconds > 0 else None
        stored = self.client.set_json(cache_key, entry.model_dump(mode="json"), ttl_seconds=ttl_seconds)
        self._record("writes" if stored else "write_failures")
        self._log(
            "cache.exact.write" if stored else "cache.exact.write_failure",
            query_context=query_context,
            cache_key=cache_key,
            answer_type=response.response.answer_type,
        )

    def build_cache_key(self, query_context: QueryContext) -> str:
        cache_key, _ = self.build_cache_identity(query_context)
        return cache_key

    def build_cache_identity(self, query_context: QueryContext) -> tuple[str, ExactCacheKeyContext]:
        key_context = self.identity_builder.build_context(query_context)
        key_hash = self.identity_builder.build_hash(key_context)
        return f"ai-legal:exact:{key_hash}", key_context

    def _record(self, event: str) -> None:
        if self.metrics_service is not None:
            self.metrics_service.record_exact(event)

    def _log(self, event: str, query_context: QueryContext, cache_key: str | None = None, **fields) -> None:
        log_event(
            logger,
            event,
            cache_key=cache_key,
            jurisdiction=query_context.jurisdiction.value,
            domain=query_context.domain.value if query_context.domain is not None else None,
            query_type=query_context.query_type.value,
            query_hash=query_context.query_hash,
            **fields,
        )
