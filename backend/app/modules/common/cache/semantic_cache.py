from datetime import UTC, datetime, timedelta
import logging

from app.modules.common.cache.client import RedisCacheClient
from app.modules.common.cache.identity import CacheIdentityBuilder
from app.modules.common.cache.schemas import ExactCacheKeyContext, SemanticCacheEntry, SemanticCacheMatch
from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.common.observability.cache_metrics import CacheMetricsService
from app.modules.common.observability.logging import log_event
from app.modules.common.qdrant.client import QdrantVectorStore
from app.modules.common.querying.schemas import QueryContext, QueryType
from app.modules.common.responses.schemas import SearchAnswerResponse


logger = logging.getLogger(__name__)


class SemanticCacheService:
    def __init__(
        self,
        client: RedisCacheClient | None,
        vector_store: QdrantVectorStore,
        embedding_service: EmbeddingService,
        enabled: bool,
        ttl_seconds: int,
        response_schema_version: str,
        strategy_prompt_version: str,
        similarity_threshold: float,
        search_limit: int,
        metrics_service: CacheMetricsService | None = None,
    ) -> None:
        self.client = client
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.enabled = enabled and client is not None
        self.ttl_seconds = ttl_seconds
        self.similarity_threshold = similarity_threshold
        self.search_limit = search_limit
        self.metrics_service = metrics_service
        self.identity_builder = CacheIdentityBuilder(
            vector_store=vector_store,
            embedding_service=embedding_service,
            response_schema_version=response_schema_version,
            strategy_prompt_version=strategy_prompt_version,
        )

    def get(self, query_context: QueryContext) -> SearchAnswerResponse | None:
        if not self._can_use(query_context):
            self._record("disabled" if not self.enabled or self.client is None else "skipped")
            self._log("cache.semantic.disabled" if not self.enabled or self.client is None else "cache.semantic.skipped", query_context=query_context)
            return None
        assert self.client is not None
        key_context = self.identity_builder.build_context(query_context)
        index_name = self._index_name(key_context)
        query_vector = self.embedding_service.embed_query(query_context.normalized_query)
        matches = self.client.search_semantic_entries(
            index_name=index_name,
            key_context=key_context,
            query_vector=query_vector,
            top_k=self.search_limit,
        )
        if not matches:
            self._record("misses")
            self._log("cache.semantic.miss", query_context=query_context, index_name=index_name)
            return None

        best_match = self._best_match(matches)
        if best_match is None or best_match.similarity < self.similarity_threshold:
            self._record("misses")
            self._log(
                "cache.semantic.threshold_miss",
                query_context=query_context,
                index_name=index_name,
                similarity=best_match.similarity if best_match is not None else None,
                similarity_threshold=self.similarity_threshold,
            )
            return None
        self._record("hits")
        self._log(
            "cache.semantic.hit",
            query_context=query_context,
            index_name=index_name,
            similarity=best_match.similarity,
        )
        return SearchAnswerResponse.model_validate(best_match.entry.response_payload)

    def set(self, query_context: QueryContext, response: SearchAnswerResponse) -> None:
        if not self._should_store(query_context, response):
            self._record("disabled" if not self.enabled or self.client is None else "skipped")
            self._log("cache.semantic.disabled" if not self.enabled or self.client is None else "cache.semantic.skipped", query_context=query_context)
            return
        assert self.client is not None
        key_context = self.identity_builder.build_context(query_context)
        index_name = self._index_name(key_context)
        query_vector = self.embedding_service.embed_query(query_context.normalized_query)
        vector_dim = len(query_vector)
        if not self.client.ensure_semantic_index(
            index_name=index_name,
            prefix=self._entry_prefix(key_context),
            vector_dim=vector_dim,
        ):
            if self.client.semantic_support_known is False:
                self._record("unsupported")
                self._log("cache.semantic.unsupported", query_context=query_context, index_name=index_name)
            else:
                self._record("write_failures")
                self._log("cache.semantic.write_failure", query_context=query_context, index_name=index_name)
            return

        cache_hash = self.identity_builder.build_hash(key_context)
        cache_key = f"{self._entry_prefix(key_context)}{cache_hash}:{query_context.query_hash}"
        created_at = datetime.now(tz=UTC)
        expires_at = created_at + timedelta(seconds=self.ttl_seconds) if self.ttl_seconds > 0 else None
        payload = response.response
        entry = SemanticCacheEntry(
            cache_key=cache_key,
            normalized_query=query_context.normalized_query,
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
        stored = self.client.upsert_semantic_entry(
            index_name=index_name,
            entry_key=cache_key,
            entry=entry,
            query_vector=query_vector,
            ttl_seconds=ttl_seconds,
        )
        self._record("writes" if stored else "write_failures")
        self._log(
            "cache.semantic.write" if stored else "cache.semantic.write_failure",
            query_context=query_context,
            index_name=index_name,
            cache_key=cache_key,
            answer_type=response.response.answer_type,
        )

    def _best_match(self, matches: list[SemanticCacheMatch]) -> SemanticCacheMatch | None:
        if not matches:
            return None
        return max(matches, key=lambda item: item.similarity)

    def _can_use(self, query_context: QueryContext) -> bool:
        return (
            self.enabled
            and self.client is not None
            and query_context.query_type != QueryType.STRATEGY
            and query_context.domain is not None
        )

    def _should_store(self, query_context: QueryContext, response: SearchAnswerResponse) -> bool:
        return (
            self._can_use(query_context)
            and response.decision.use_llm is False
            and response.response.answer_type != "strategy_answer"
        )

    @staticmethod
    def _index_name(key_context: ExactCacheKeyContext) -> str:
        fingerprint = key_context.embedding_fingerprint.replace("-", "_")
        return f"idx:ai_legal:semantic:{fingerprint}"

    @staticmethod
    def _entry_prefix(key_context: ExactCacheKeyContext) -> str:
        fingerprint = key_context.embedding_fingerprint.replace("-", "_")
        return f"ai-legal:semantic:{fingerprint}:"

    def _record(self, event: str) -> None:
        if self.metrics_service is not None:
            self.metrics_service.record_semantic(event)

    def _log(
        self,
        event: str,
        query_context: QueryContext,
        index_name: str | None = None,
        cache_key: str | None = None,
        **fields,
    ) -> None:
        log_event(
            logger,
            event,
            index_name=index_name,
            cache_key=cache_key,
            jurisdiction=query_context.jurisdiction.value,
            domain=query_context.domain.value if query_context.domain is not None else None,
            query_type=query_context.query_type.value,
            query_hash=query_context.query_hash,
            **fields,
        )
