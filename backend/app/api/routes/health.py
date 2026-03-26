from fastapi import APIRouter, Depends

from app.core.config import Settings
from app.core.dependencies import (
    get_app_settings,
    get_cache_metrics_service,
    get_qdrant_vector_store,
    get_redis_cache_client,
)
from app.modules.common.cache.client import RedisCacheClient
from app.modules.common.observability.cache_metrics import CacheMetricsService
from app.modules.common.observability.status import build_cache_runtime_status
from app.modules.common.qdrant.client import QdrantVectorStore


router = APIRouter()


@router.get("/health")
def health_check(
    settings: Settings = Depends(get_app_settings),
    metrics_service: CacheMetricsService = Depends(get_cache_metrics_service),
    vector_store: QdrantVectorStore = Depends(get_qdrant_vector_store),
    redis_client: RedisCacheClient | None = Depends(get_redis_cache_client),
):
    return {
        "status": "ok",
        "environment": settings.app_env,
        "storage_path": str(settings.storage_path_obj),
        "qdrant": "up" if vector_store.health_check() else "down",
        "cache": build_cache_runtime_status(
            settings=settings,
            redis_client=redis_client,
            vector_store=vector_store,
        ).model_dump(mode="json"),
        "metrics": metrics_service.snapshot().model_dump(mode="json"),
    }
