from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import CountryEnum, DomainEnum


class ChunkPayload(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    chunk_id: str
    document_id: str
    filename: str
    country: CountryEnum
    domain: DomainEnum
    jurisdiction_module: str
    text: str
    chunk_index: int
    source_type: str
    source: str | None = None
    case_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class EmbeddedChunk(BaseModel):
    id: str
    vector: list[float]
    payload: ChunkPayload


class SearchRequest(BaseModel):
    query: str
    country: CountryEnum | None = None
    domain: DomainEnum | None = None
    document_ids: list[str] = Field(default_factory=list)
    case_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=25)


class SearchResultItem(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    country: CountryEnum
    domain: DomainEnum
    jurisdiction_module: str
    text: str
    chunk_index: int
    source_type: str
    source: str | None = None
    case_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    score: float


class RankedSearchResult(BaseModel):
    item: SearchResultItem
    dense_rank: int
    dense_score: float
    lexical_rank: int
    lexical_score: float
    fused_score: float
    overlap_count: int = 0
    overlap_ratio: float = 0.0
    phrase_match: bool = False
    citation_match: bool = False
    filename_match: bool = False
    source_match: bool = False


class RetrievalFeatureSet(BaseModel):
    top_dense_score: float = 0.0
    top_fused_score: float = 0.0
    score_gap: float = 0.0
    keyword_coverage: float = 0.0
    phrase_match: bool = False
    citation_match: bool = False
    domain_consistency: float = 0.0
    supporting_chunks: int = 0


class HybridSearchResponse(BaseModel):
    results: list[SearchResultItem] = Field(default_factory=list)
    ranked_results: list[RankedSearchResult] = Field(default_factory=list)
    features: RetrievalFeatureSet = Field(default_factory=RetrievalFeatureSet)


class SearchResponse(BaseModel):
    results: list[SearchResultItem]


class CollectionEmbeddingMetadata(BaseModel):
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    embedding_revision: str
    embedding_fingerprint: str


class ReindexRequest(BaseModel):
    delete_previous_collection: bool = False


class ReindexResponse(BaseModel):
    status: str
    alias_name: str
    source_collection: str | None = None
    target_collection: str
    documents_total: int
    documents_reindexed: int
