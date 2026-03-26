from datetime import datetime

from pydantic import BaseModel, Field


class ExactCacheKeyContext(BaseModel):
    query_hash: str
    jurisdiction: str
    domain: str
    query_type: str
    active_collection: str
    corpus_fingerprint: str
    embedding_fingerprint: str
    response_schema_version: str
    prompt_version: str | None = None


class ExactCacheEntry(BaseModel):
    cache_key: str
    jurisdiction: str
    domain: str
    query_type: str
    active_collection: str
    corpus_fingerprint: str
    embedding_fingerprint: str
    response_schema_version: str
    prompt_version: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    response_payload: dict
    created_at: datetime
    expires_at: datetime | None = None


class SemanticCacheEntry(BaseModel):
    cache_key: str
    normalized_query: str
    jurisdiction: str
    domain: str
    query_type: str
    active_collection: str
    corpus_fingerprint: str
    embedding_fingerprint: str
    response_schema_version: str
    prompt_version: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    response_payload: dict
    created_at: datetime
    expires_at: datetime | None = None


class SemanticCacheMatch(BaseModel):
    entry: SemanticCacheEntry
    distance: float
    similarity: float
