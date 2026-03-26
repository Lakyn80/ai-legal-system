from enum import Enum

from pydantic import BaseModel, Field

from app.core.enums import CountryEnum, DomainEnum


class QueryType(str, Enum):
    EXACT_STATUTE = "exact_statute"
    SEMANTIC_LAW = "semantic_law"
    CASE_LOOKUP = "case_lookup"
    STRATEGY = "strategy"


class QueryContext(BaseModel):
    raw_query: str
    normalized_query: str
    query_hash: str
    query_type: QueryType
    domain: DomainEnum | None = None
    jurisdiction: CountryEnum
    citation_patterns: list[str] = Field(default_factory=list)
    keyword_terms: list[str] = Field(default_factory=list)
    expects_deterministic_answer: bool = False
