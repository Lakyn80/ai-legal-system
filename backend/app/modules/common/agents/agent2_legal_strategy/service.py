"""
Agent 2 runner — structured LLM call, validation, evidence contract, optional repair.

Does not perform retrieval. Does not log full case text by default.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.modules.common.agents.agent2_legal_strategy.errors import (
    Agent2InvocationError,
    Agent2OutputContractError,
    Agent2ValidationError,
)
from app.modules.common.agents.agent2_legal_strategy.evidence_contract import (
    allowed_provision_keys,
    contract_violations,
    format_allowed_provisions_list,
)
from app.modules.common.agents.agent2_legal_strategy.input_schemas import LegalStrategyAgent2Input
from app.modules.common.agents.agent2_legal_strategy.prompts import (
    AGENT2_SYSTEM_PROMPT_VERSION,
    USER_MESSAGE_FOOTER,
    USER_MESSAGE_HEADER,
    build_repair_addon,
    build_system_prompt,
)
from app.modules.common.agents.agent2_legal_strategy.schemas import LegalStrategyAgent2Output
from app.modules.common.agents.agent2_legal_strategy.telemetry import (
    Agent2AuditRecord,
    emit_audit_log,
    fingerprint_case_id,
    now_iso,
)
from app.modules.common.llm.provider import BaseLLMProvider

log = logging.getLogger(__name__)


def _output_schema_version() -> str:
    info = LegalStrategyAgent2Output.model_fields.get("schema_version")
    if info is None:
        return "agent2_legal_strategy.v1"
    d = info.default
    return d if isinstance(d, str) else "agent2_legal_strategy.v1"


@dataclass
class LegalStrategyAgent2RunResult:
    """Validated Agent 2 output plus audit metadata."""

    output: LegalStrategyAgent2Output
    audit: Agent2AuditRecord


@dataclass(frozen=True)
class Agent2RunConfig:
    """Execution knobs (extensible without breaking callers)."""

    strict_reliability: bool = True
    max_repair_attempts: int = 1
    prompt_version: str = AGENT2_SYSTEM_PROMPT_VERSION
    # Future: strategy_mode: Literal["conservative", "neutral", "aggressive"]


class LegalStrategyAgent2Service:
    """
    Production entry: typed input → structured output + audit record.
    """

    def __init__(
        self,
        llm: BaseLLMProvider,
        *,
        model_name: str = "unknown",
    ) -> None:
        self._llm = llm
        self._model_name = model_name

    def run(
        self,
        inp: LegalStrategyAgent2Input,
        *,
        config: Agent2RunConfig | None = None,
    ) -> LegalStrategyAgent2RunResult:
        cfg = config or Agent2RunConfig()
        started = now_iso()
        case_fp = fingerprint_case_id(inp.case_id)

        user_message = self._build_user_message(inp)
        system_prompt = build_system_prompt(
            strict_reliability=cfg.strict_reliability,
            prompt_version=cfg.prompt_version,
        )

        repair_count = 0
        validation_ok = True

        try:
            out = self._invoke_structured_safe(system_prompt, user_message)
        except Agent2InvocationError as e:
            emit_audit_log(
                self._make_audit(
                    inp=inp,
                    case_fp=case_fp,
                    started=started,
                    finished=now_iso(),
                    validation_ok=False,
                    repair_count=0,
                    contract_ok=False,
                    violation_n=0,
                    error_code=e.code,
                    prompt_version=cfg.prompt_version,
                )
            )
            raise
        except ValidationError as e:
            emit_audit_log(
                self._make_audit(
                    inp=inp,
                    case_fp=case_fp,
                    started=started,
                    finished=now_iso(),
                    validation_ok=False,
                    repair_count=0,
                    contract_ok=False,
                    violation_n=0,
                    error_code="agent2_validation_failed",
                    prompt_version=cfg.prompt_version,
                )
            )
            raise Agent2ValidationError(f"Structured output validation failed: {e}") from e

        violations = contract_violations(inp, out)
        while violations and repair_count < cfg.max_repair_attempts:
            repair_count += 1
            log.warning(
                "agent2_contract_repair case_id_fp=%s attempt=%s violations=%s",
                case_fp,
                repair_count,
                len(violations),
            )
            repair_system = (
                system_prompt
                + "\n"
                + build_repair_addon(
                    format_allowed_provisions_list(inp),
                    "; ".join(violations[:5]),
                )
            )
            try:
                out = self._invoke_structured_safe(repair_system, user_message)
            except (Agent2InvocationError, ValidationError) as e:
                last_error = str(e)
                raise Agent2ValidationError(f"Repair invocation failed: {e}") from e
            violations = contract_violations(inp, out)

        contract_ok = not violations
        if not contract_ok:
            err = Agent2OutputContractError(
                "Structured output cites provisions not present in legal_evidence_pack.",
                violations=violations,
            )
            finished = now_iso()
            audit = self._make_audit(
                inp=inp,
                case_fp=case_fp,
                started=started,
                finished=finished,
                validation_ok=validation_ok,
                repair_count=repair_count,
                contract_ok=False,
                violation_n=len(violations),
                error_code=err.code,
                prompt_version=cfg.prompt_version,
            )
            emit_audit_log(audit)
            raise err

        finished = now_iso()
        audit = self._make_audit(
            inp=inp,
            case_fp=case_fp,
            started=started,
            finished=finished,
            validation_ok=validation_ok,
            repair_count=repair_count,
            contract_ok=True,
            violation_n=0,
            error_code=None,
            prompt_version=cfg.prompt_version,
        )
        emit_audit_log(audit)
        return LegalStrategyAgent2RunResult(output=out, audit=audit)

    def _invoke_structured_safe(
        self,
        system_prompt: str,
        user_message: str,
    ) -> LegalStrategyAgent2Output:
        try:
            return self._llm.invoke_structured(
                system_prompt,
                user_message,
                LegalStrategyAgent2Output,
            )
        except ValidationError as e:
            raise Agent2ValidationError(str(e)) from e
        except Exception as e:
            log.exception("agent2_llm_invoke_failed")
            raise Agent2InvocationError(f"LLM invocation failed: {e}") from e

    def _build_user_message(self, inp: LegalStrategyAgent2Input) -> str:
        """
        Serialize input as JSON inside explicit delimiters so case text is data, not instructions.
        """
        payload: dict[str, Any] = inp.model_dump(mode="json")
        inner = json.dumps(payload, ensure_ascii=False, indent=2)
        return f"{USER_MESSAGE_HEADER}{inner}{USER_MESSAGE_FOOTER}"

    def _make_audit(
        self,
        *,
        inp: LegalStrategyAgent2Input,
        case_fp: str,
        started: str,
        finished: str,
        validation_ok: bool,
        repair_count: int,
        contract_ok: bool,
        violation_n: int,
        error_code: str | None,
        prompt_version: str,
    ) -> Agent2AuditRecord:
        return Agent2AuditRecord(
            case_id_fp=case_fp,
            jurisdiction=inp.jurisdiction[:128],
            prompt_version=prompt_version[:64],
            schema_version=_output_schema_version(),
            model_name=self._model_name[:128],
            validation_ok=validation_ok,
            repair_count=repair_count,
            contract_ok=contract_ok,
            contract_violation_count=violation_n,
            started_at_iso=started,
            finished_at_iso=finished,
            error_code=error_code,
            input_summary=Agent2AuditRecord.build_input_summary(
                facts_n=len(inp.facts),
                flags_n=len(inp.issue_flags),
                provisions_n=len(allowed_provision_keys(inp)),
                summary_len=len(inp.cleaned_summary or ""),
            ),
        )
