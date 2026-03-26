from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.qdrant.schemas import SearchResultItem


class StrategyRequest(BaseModel):
    query: str
    country: CountryEnum | None = None
    domain: DomainEnum | None = None
    document_ids: list[str] = Field(default_factory=list)
    case_id: str | None = None
    top_k: int = Field(default=6, ge=2, le=20)


class StrategyResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    jurisdiction: CountryEnum
    domain: str = "mixed"
    summary: str
    facts: list[str] = Field(default_factory=list)
    relevant_laws: list[str] = Field(default_factory=list)
    relevant_court_positions: list[str] = Field(default_factory=list)
    arguments_for_client: list[str] = Field(default_factory=list)
    arguments_against_client: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class StrategyResponse(BaseModel):
    strategy: StrategyResult
    retrieved_chunks: list[SearchResultItem] = Field(default_factory=list)


class JurisdictionInfo(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    country: CountryEnum
    label: str
    description: str
    supported_domains: list[DomainEnum]
