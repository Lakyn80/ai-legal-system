"""Domain errors for Agent 2 (legal strategy builder)."""

from __future__ import annotations


class Agent2Error(Exception):
    """Base class for Agent 2 failures."""

    def __init__(self, message: str, *, code: str = "agent2_error") -> None:
        super().__init__(message)
        self.code = code


class Agent2InputError(Agent2Error):
    """Invalid or unusable input payload."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="agent2_input_invalid")


class Agent2InvocationError(Agent2Error):
    """LLM provider failed (network, API, or non-parseable structured output)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="agent2_invocation_failed")


class Agent2ValidationError(Agent2Error):
    """Structured output failed Pydantic validation after repair."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="agent2_validation_failed")


class Agent2OutputContractError(Agent2Error):
    """
    Model output cites legal provisions not present in the supplied evidence pack,
    after repair attempts exhausted.
    """

    def __init__(self, message: str, *, violations: list[str] | None = None) -> None:
        super().__init__(message, code="agent2_output_contract_violation")
        self.violations = violations or []
