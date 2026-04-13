"""
Agent 2 — legal strategy / reasoner over a closed evidence pack (no broad retrieval).

Public API: input schema, output schema, service runner, errors, audit types.
"""

from app.modules.common.agents.agent2_legal_strategy.errors import (
    Agent2Error,
    Agent2InvocationError,
    Agent2OutputContractError,
    Agent2ValidationError,
)
from app.modules.common.agents.agent2_legal_strategy.input_schemas import (
    LegalEvidencePack,
    LegalStrategyAgent2Input,
    RetrievedArticleExcerpt,
)
from app.modules.common.agents.agent2_legal_strategy.prompts import AGENT2_SYSTEM_PROMPT_VERSION
from app.modules.common.agents.agent2_legal_strategy.schemas import LegalStrategyAgent2Output
from app.modules.common.agents.agent2_legal_strategy.service import (
    Agent2RunConfig,
    LegalStrategyAgent2RunResult,
    LegalStrategyAgent2Service,
)
from app.modules.common.agents.agent2_legal_strategy.telemetry import Agent2AuditRecord

__all__ = [
    "AGENT2_SYSTEM_PROMPT_VERSION",
    "Agent2AuditRecord",
    "Agent2Error",
    "Agent2InvocationError",
    "Agent2OutputContractError",
    "Agent2RunConfig",
    "Agent2ValidationError",
    "LegalEvidencePack",
    "LegalStrategyAgent2Input",
    "LegalStrategyAgent2Output",
    "LegalStrategyAgent2RunResult",
    "LegalStrategyAgent2Service",
    "RetrievedArticleExcerpt",
]
