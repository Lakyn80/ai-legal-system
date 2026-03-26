from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConfidenceDecision(BaseModel):
    level: ConfidenceLevel
    use_llm: bool
    response_type: Literal["citation_answer", "semantic_explanation", "strategy_answer"]
    reason_codes: list[str] = Field(default_factory=list)
    score_summary: dict[str, float | bool | int] = Field(default_factory=dict)
