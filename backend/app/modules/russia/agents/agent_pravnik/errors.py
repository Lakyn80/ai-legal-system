"""Domain errors for agent_pravnik (Russian litigation drafting)."""

from __future__ import annotations


class PravnikError(Exception):
    """Base class for agent_pravnik failures."""

    def __init__(self, message: str, *, code: str = "pravnik_error") -> None:
        super().__init__(message)
        self.code = code


class PravnikInputError(PravnikError):
    """Invalid input payload."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="pravnik_input_invalid")


class PravnikInvocationError(PravnikError):
    """LLM provider failed."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="pravnik_invocation_failed")


class PravnikValidationError(PravnikError):
    """Structured output failed validation after repair."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="pravnik_validation_failed")


class PravnikOutputContractError(PravnikError):
    """Output cites provisions not in evidence pack."""

    def __init__(self, message: str, *, violations: list[str] | None = None) -> None:
        super().__init__(message, code="pravnik_output_contract_violation")
        self.violations = violations or []
