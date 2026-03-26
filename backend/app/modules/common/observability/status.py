from app.core.config import Settings
from app.modules.common.cache.client import RedisCacheClient
from app.modules.common.observability.schemas import CacheRuntimeStatus
from app.modules.common.qdrant.client import QdrantVectorStore


def build_cache_runtime_status(
    settings: Settings,
    redis_client: RedisCacheClient | None,
    vector_store: QdrantVectorStore,
) -> CacheRuntimeStatus:
    metadata = vector_store.get_active_collection_metadata()
    return CacheRuntimeStatus(
        redis_enabled=settings.redis_enabled,
        redis_reachable=redis_client.ping() if redis_client is not None else False,
        exact_cache_enabled=settings.redis_enabled and settings.exact_cache_enabled,
        semantic_cache_enabled=settings.redis_enabled and settings.semantic_cache_enabled,
        semantic_search_supported=(
            redis_client.semantic_search_supported() if redis_client is not None else None
        ),
        active_collection=vector_store.get_active_collection_name(),
        embedding_fingerprint=metadata.embedding_fingerprint if metadata is not None else None,
    )
