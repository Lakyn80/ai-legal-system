import hashlib
import json

from app.modules.common.cache.schemas import ExactCacheKeyContext
from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.common.qdrant.client import QdrantVectorStore
from app.modules.common.querying.schemas import QueryContext


class CacheIdentityBuilder:
    def __init__(
        self,
        vector_store: QdrantVectorStore,
        embedding_service: EmbeddingService,
        response_schema_version: str,
        strategy_prompt_version: str,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.response_schema_version = response_schema_version
        self.strategy_prompt_version = strategy_prompt_version

    def build_context(self, query_context: QueryContext) -> ExactCacheKeyContext:
        active_collection = self.vector_store.get_active_collection_name() or self.vector_store.alias_name
        metadata = self.vector_store.get_active_collection_metadata()
        embedding_fingerprint = (
            metadata.embedding_fingerprint if metadata else self.embedding_service.profile.fingerprint
        )
        corpus_fingerprint = f"{active_collection}:{embedding_fingerprint}"
        return ExactCacheKeyContext(
            query_hash=query_context.query_hash,
            jurisdiction=query_context.jurisdiction.value,
            domain=query_context.domain.value if query_context.domain else "mixed",
            query_type=query_context.query_type.value,
            active_collection=active_collection,
            corpus_fingerprint=corpus_fingerprint,
            embedding_fingerprint=embedding_fingerprint,
            response_schema_version=self.response_schema_version,
            prompt_version=self.strategy_prompt_version if query_context.query_type.value == "strategy" else None,
        )

    def build_hash(self, key_context: ExactCacheKeyContext) -> str:
        payload = key_context.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
