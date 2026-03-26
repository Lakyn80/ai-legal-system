from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Legal System Backend"
    app_env: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api"
    backend_cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    storage_path: str = "/app/storage"

    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "legal_documents"
    qdrant_collection_alias: str | None = None
    redis_enabled: bool = False
    redis_url: str = "redis://redis:6379/0"
    exact_cache_enabled: bool = False
    exact_cache_ttl_seconds: int = 3600
    semantic_cache_enabled: bool = False
    semantic_cache_ttl_seconds: int = 7200
    semantic_cache_similarity_threshold: float = 0.93
    semantic_cache_top_k: int = 3
    response_schema_version: str = "v1"
    strategy_prompt_version: str = "v1"

    embedding_provider: str = "hash"
    embedding_model: str = Field(
        default="Alibaba-NLP/gte-multilingual-base",
        validation_alias=AliasChoices("EMBEDDING_MODEL_NAME", "EMBEDDING_MODEL"),
    )
    embedding_fallback_provider: str | None = "hash"
    embedding_hash_dimension: int = 384
    llm_provider: str = "mock"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None

    chunk_size: int = 1200
    chunk_overlap: int = 180
    top_k_default: int = 6

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("embedding_provider", mode="before")
    @classmethod
    def normalize_embedding_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"sentence_transformer", "sentence_transformers"}:
            return "sentence_transformer"
        return normalized

    @field_validator("embedding_fallback_provider", mode="before")
    @classmethod
    def normalize_blank_fallback(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        lowered = normalized.lower()
        if lowered in {"sentence_transformer", "sentence_transformers"}:
            return "sentence_transformer"
        return lowered or None

    @property
    def storage_path_obj(self) -> Path:
        return Path(self.storage_path)

    @property
    def qdrant_collection_alias_name(self) -> str:
        if self.qdrant_collection_alias:
            return self.qdrant_collection_alias
        return f"{self.qdrant_collection}_active"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
