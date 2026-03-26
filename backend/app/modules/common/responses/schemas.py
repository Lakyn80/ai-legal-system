from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.common.querying.schemas import QueryContext
from app.modules.common.qdrant.schemas import SearchResultItem
from app.modules.common.reasoning.schemas import ConfidenceDecision


class SourceReference(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    source: str | None = None
    score: float


class ResponseProvenance(BaseModel):
    llm_used: bool
    retrieval_mode: str = "hybrid"
    reason_codes: list[str] = Field(default_factory=list)
    model_name: str | None = None


class CitationAnswer(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    answer_type: Literal["citation_answer"] = "citation_answer"
    jurisdiction: str
    domain: str
    query: str
    answer: str
    citations: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: ResponseProvenance
    sources: list[SourceReference] = Field(default_factory=list)


class SemanticExplanation(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    answer_type: Literal["semantic_explanation"] = "semantic_explanation"
    jurisdiction: str
    domain: str
    query: str
    summary: str
    explanation: str
    key_points: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: ResponseProvenance
    sources: list[SourceReference] = Field(default_factory=list)


class StrategyAnswerPayload(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    answer_type: Literal["strategy_answer"] = "strategy_answer"
    jurisdiction: str
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
    document_ids: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    provenance: ResponseProvenance
    sources: list[SourceReference] = Field(default_factory=list)


StructuredAnswer = Annotated[
    CitationAnswer | SemanticExplanation | StrategyAnswerPayload,
    Field(discriminator="answer_type"),
]


class SearchAnswerResponse(BaseModel):
    query_context: QueryContext
    decision: ConfidenceDecision
    response: StructuredAnswer
    results: list[SearchResultItem] = Field(default_factory=list)
