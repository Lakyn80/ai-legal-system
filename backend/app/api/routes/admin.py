from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from app.core.config import Settings
from app.core.dependencies import (
    get_app_settings,
    get_cache_admin_service,
    get_cache_metrics_service,
    get_qdrant_vector_store,
    get_redis_cache_client,
    get_reindex_service,
)
from app.modules.common.cache.admin_service import CacheAdminService
from app.modules.common.observability.cache_metrics import CacheMetricsService
from app.modules.common.observability.status import build_cache_runtime_status
from app.modules.common.qdrant.schemas import ReindexRequest, ReindexResponse

if TYPE_CHECKING:
    from app.modules.common.cache.client import RedisCacheClient
    from app.modules.common.qdrant.client import QdrantVectorStore
    from app.modules.common.qdrant.reindex_service import CollectionReindexService


router = APIRouter()


@router.post("/reindex", response_model=ReindexResponse)
def reindex_documents(
    request: ReindexRequest,
    reindex_service: CollectionReindexService = Depends(get_reindex_service),
):
    return reindex_service.reindex(delete_previous_collection=request.delete_previous_collection)


@router.get("/cache/metrics")
def get_cache_metrics(
    settings: Settings = Depends(get_app_settings),
    metrics_service: CacheMetricsService = Depends(get_cache_metrics_service),
    vector_store: QdrantVectorStore = Depends(get_qdrant_vector_store),
    redis_client: RedisCacheClient | None = Depends(get_redis_cache_client),
):
    return {
        "runtime": build_cache_runtime_status(
            settings=settings,
            redis_client=redis_client,
            vector_store=vector_store,
        ).model_dump(mode="json"),
        "metrics": metrics_service.snapshot().model_dump(mode="json"),
    }


@router.post("/cache/reset")
def reset_cache(
    settings: Settings = Depends(get_app_settings),
    cache_admin_service: CacheAdminService = Depends(get_cache_admin_service),
    vector_store: QdrantVectorStore = Depends(get_qdrant_vector_store),
    redis_client: RedisCacheClient | None = Depends(get_redis_cache_client),
):
    reset_result = cache_admin_service.reset()
    return {
        "status": "ok",
        "cleared": reset_result.model_dump(mode="json"),
        "runtime": build_cache_runtime_status(
            settings=settings,
            redis_client=redis_client,
            vector_store=vector_store,
        ).model_dump(mode="json"),
    }


@router.post("/cache/metrics/reset")
def reset_cache_metrics(
    metrics_service: CacheMetricsService = Depends(get_cache_metrics_service),
):
    return {
        "status": "ok",
        "metrics": metrics_service.reset().model_dump(mode="json"),
    }
