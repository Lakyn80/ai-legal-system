from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.core.config import Settings, get_settings

if TYPE_CHECKING:
    from app.modules.common.cache.admin_service import CacheAdminService
    from app.modules.common.cache.client import RedisCacheClient
    from app.modules.common.cache.exact_cache import ExactCacheService
    from app.modules.common.cache.semantic_cache import SemanticCacheService
    from app.modules.common.chunking.service import TextChunkingService
    from app.modules.common.documents.ingestion_service import DocumentIngestionService
    from app.modules.common.documents.repository import FileDocumentRepository
    from app.modules.common.documents.service import DocumentService
    from app.modules.common.embeddings.provider import EmbeddingService
    from app.modules.common.graph.strategy_engine import StrategyEngine
    from app.modules.common.observability.cache_metrics import CacheMetricsService
    from app.modules.common.orchestration.search_pipeline import SearchAnswerService
    from app.modules.common.parsing.service import DocumentParserService
    from app.modules.common.qdrant.client import QdrantVectorStore
    from app.modules.common.qdrant.reindex_service import CollectionReindexService
    from app.modules.common.qdrant.retrieval_service import RetrievalService
    from app.modules.common.querying.service import QueryProcessingService
    from app.modules.common.reasoning.confidence import ConfidenceGate
    from app.modules.common.responses.builders import SearchResponseBuilder
    from app.modules.common.storage.file_storage import FileStorageService
    from app.modules.czechia.retrieval.service import CzechLawRetrievalService
    from app.modules.registry import JurisdictionRegistry


@lru_cache(maxsize=1)
def get_storage_service() -> FileStorageService:
    from app.modules.common.storage.file_storage import FileStorageService

    settings = get_settings()
    return FileStorageService(settings.storage_path_obj)


@lru_cache(maxsize=1)
def get_document_repository() -> FileDocumentRepository:
    from app.modules.common.documents.repository import FileDocumentRepository

    return FileDocumentRepository(get_storage_service())


@lru_cache(maxsize=1)
def get_document_service() -> DocumentService:
    from app.modules.common.documents.service import DocumentService

    return DocumentService(
        storage_service=get_storage_service(),
        document_repository=get_document_repository(),
    )


@lru_cache(maxsize=1)
def get_parser_service() -> DocumentParserService:
    from app.modules.common.parsing.service import DocumentParserService

    return DocumentParserService()


@lru_cache(maxsize=1)
def get_chunking_service() -> TextChunkingService:
    from app.modules.common.chunking.service import TextChunkingService

    settings = get_settings()
    return TextChunkingService(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    from app.modules.common.embeddings.provider import EmbeddingService

    settings = get_settings()
    return EmbeddingService(
        model_name=settings.embedding_model,
        provider_name=settings.embedding_provider,
        fallback_provider_name=settings.embedding_fallback_provider,
        hash_dimension=settings.embedding_hash_dimension,
    )


@lru_cache(maxsize=1)
def get_qdrant_vector_store() -> QdrantVectorStore:
    from app.modules.common.qdrant.client import QdrantVectorStore

    settings = get_settings()
    return QdrantVectorStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection_name=settings.qdrant_collection,
        alias_name=settings.qdrant_collection_alias_name,
    )


@lru_cache(maxsize=1)
def get_redis_cache_client() -> RedisCacheClient | None:
    from app.modules.common.cache.client import RedisCacheClient

    settings = get_settings()
    if not settings.redis_enabled:
        return None
    return RedisCacheClient(url=settings.redis_url, enabled=True)


@lru_cache(maxsize=1)
def get_cache_metrics_service() -> CacheMetricsService:
    from app.modules.common.observability.cache_metrics import CacheMetricsService

    return CacheMetricsService()


@lru_cache(maxsize=1)
def get_cache_admin_service() -> CacheAdminService:
    from app.modules.common.cache.admin_service import CacheAdminService

    return CacheAdminService(get_redis_cache_client())


@lru_cache(maxsize=1)
def get_retrieval_service() -> RetrievalService:
    from app.modules.common.qdrant.retrieval_service import RetrievalService

    return RetrievalService(
        embedding_service=get_embedding_service(),
        vector_store=get_qdrant_vector_store(),
    )


@lru_cache(maxsize=1)
def get_ingestion_service() -> DocumentIngestionService:
    from app.modules.common.documents.ingestion_service import DocumentIngestionService

    return DocumentIngestionService(
        document_repository=get_document_repository(),
        parser_service=get_parser_service(),
        chunking_service=get_chunking_service(),
        embedding_service=get_embedding_service(),
        vector_store=get_qdrant_vector_store(),
    )


@lru_cache(maxsize=1)
def get_reindex_service() -> CollectionReindexService:
    from app.modules.common.qdrant.reindex_service import CollectionReindexService

    return CollectionReindexService(
        document_repository=get_document_repository(),
        ingestion_service=get_ingestion_service(),
        embedding_service=get_embedding_service(),
        vector_store=get_qdrant_vector_store(),
    )


@lru_cache(maxsize=1)
def get_llm_provider():
    from app.modules.common.llm.provider import build_llm_provider

    return build_llm_provider(get_settings())


@lru_cache(maxsize=1)
def get_jurisdiction_registry() -> JurisdictionRegistry:
    from app.modules.registry import JurisdictionRegistry

    return JurisdictionRegistry()


@lru_cache(maxsize=1)
def get_query_processing_service() -> QueryProcessingService:
    from app.modules.common.querying.service import QueryProcessingService

    return QueryProcessingService(registry=get_jurisdiction_registry())


@lru_cache(maxsize=1)
def get_confidence_gate() -> ConfidenceGate:
    from app.modules.common.reasoning.confidence import ConfidenceGate

    return ConfidenceGate()


@lru_cache(maxsize=1)
def get_search_response_builder() -> SearchResponseBuilder:
    from app.modules.common.responses.builders import SearchResponseBuilder

    return SearchResponseBuilder()


@lru_cache(maxsize=1)
def get_exact_cache_service() -> ExactCacheService:
    from app.modules.common.cache.exact_cache import ExactCacheService

    settings = get_settings()
    return ExactCacheService(
        client=get_redis_cache_client(),
        vector_store=get_qdrant_vector_store(),
        embedding_service=get_embedding_service(),
        enabled=settings.redis_enabled and settings.exact_cache_enabled,
        ttl_seconds=settings.exact_cache_ttl_seconds,
        response_schema_version=settings.response_schema_version,
        strategy_prompt_version=settings.strategy_prompt_version,
        metrics_service=get_cache_metrics_service(),
    )


@lru_cache(maxsize=1)
def get_semantic_cache_service() -> SemanticCacheService:
    from app.modules.common.cache.semantic_cache import SemanticCacheService

    settings = get_settings()
    return SemanticCacheService(
        client=get_redis_cache_client(),
        vector_store=get_qdrant_vector_store(),
        embedding_service=get_embedding_service(),
        enabled=settings.redis_enabled and settings.semantic_cache_enabled,
        ttl_seconds=settings.semantic_cache_ttl_seconds,
        response_schema_version=settings.response_schema_version,
        strategy_prompt_version=settings.strategy_prompt_version,
        similarity_threshold=settings.semantic_cache_similarity_threshold,
        search_limit=settings.semantic_cache_top_k,
        metrics_service=get_cache_metrics_service(),
    )


@lru_cache(maxsize=1)
def get_strategy_engine() -> StrategyEngine:
    from app.modules.common.graph.strategy_engine import StrategyEngine

    return StrategyEngine(
        registry=get_jurisdiction_registry(),
        retrieval_service=get_retrieval_service(),
        llm_provider=get_llm_provider(),
    )


@lru_cache(maxsize=1)
def get_search_answer_service() -> SearchAnswerService:
    from app.modules.common.orchestration.search_pipeline import SearchAnswerService

    settings = get_settings()
    return SearchAnswerService(
        query_processing_service=get_query_processing_service(),
        retrieval_service=get_retrieval_service(),
        confidence_gate=get_confidence_gate(),
        response_builder=get_search_response_builder(),
        llm_provider=get_llm_provider(),
        strategy_engine=get_strategy_engine(),
        llm_model_name=settings.llm_model,
        exact_cache_service=get_exact_cache_service(),
        semantic_cache_service=get_semantic_cache_service(),
        metrics_service=get_cache_metrics_service(),
    )


@lru_cache(maxsize=1)
def get_czech_law_retrieval_service() -> CzechLawRetrievalService:
    from app.modules.czechia.retrieval.dense_retriever import CzechLawDenseRetriever
    from app.modules.czechia.retrieval.service import CzechLawRetrievalService

    settings = get_settings()
    dense_retriever = CzechLawDenseRetriever(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )
    return CzechLawRetrievalService(
        embedding_service=get_embedding_service(),
        dense_retriever=dense_retriever,
    )


@lru_cache(maxsize=1)
def get_czech_search_answer_service() -> SearchAnswerService:
    from app.modules.czechia.retrieval.adapter import CzechLawRetrievalAdapter
    from app.modules.common.orchestration.search_pipeline import SearchAnswerService

    settings = get_settings()
    adapter = CzechLawRetrievalAdapter(get_czech_law_retrieval_service())
    return SearchAnswerService(
        query_processing_service=get_query_processing_service(),
        retrieval_service=adapter,
        confidence_gate=get_confidence_gate(),
        response_builder=get_search_response_builder(),
        llm_provider=get_llm_provider(),
        strategy_engine=get_strategy_engine(),
        llm_model_name=settings.llm_model,
        exact_cache_service=get_exact_cache_service(),
        semantic_cache_service=get_semantic_cache_service(),
        metrics_service=get_cache_metrics_service(),
    )


def get_app_settings() -> Settings:
    return get_settings()
