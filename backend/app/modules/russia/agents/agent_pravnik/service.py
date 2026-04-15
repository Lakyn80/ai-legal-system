"""
agent_pravnik service — structured LLM drafting, contract + quality gates, repair loop, fallback.
Uses the same BaseLLMProvider as Agent 2 (OpenAI-compatible; GPT-5.4 / Claude adapters elsewhere).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import ValidationError

from app.modules.common.agents.agent2_legal_strategy.evidence_contract import allowed_provision_keys
from app.modules.common.llm.provider import BaseLLMProvider

from app.modules.russia.agents.agent_pravnik.errors import (
    PravnikInputError,
    PravnikInvocationError,
    PravnikValidationError,
)
from app.modules.russia.agents.agent_pravnik.fallback_ru import build_deterministic_fallback
from app.modules.russia.agents.agent_pravnik.prompts_ru import (
    PRAVNIK_SYSTEM_PROMPT_VERSION,
    SYSTEM_PRAVNIK_RU,
    build_repair_addon_ru,
    build_user_message,
)
from app.modules.russia.agents.agent_pravnik.quality_gates import cyrillic_ratio, quality_gate_violations
from app.modules.russia.agents.agent_pravnik.schemas import AgentPravnikRuInput, AgentPravnikRuOutput, PRAVNIK_SCHEMA_VERSION
from app.modules.russia.agents.agent_pravnik.telemetry import (
    PravnikAuditRecord,
    emit_audit_log,
    emit_draft_rejected,
    emit_fallback,
    fingerprint_case_id,
    now_iso,
)
from app.modules.russia.agents.agent_pravnik.validators import _bridge_legal_strategy_input, pravnik_contract_violations

log = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3  # first + up to 2 repairs (plan §10.2)


@dataclass(frozen=True)
class PravnikRunConfig:
    prompt_version: str = PRAVNIK_SYSTEM_PROMPT_VERSION
    model_name: str = "unknown"


@dataclass
class AgentPravnikRunResult:
    output: AgentPravnikRuOutput
    audit: PravnikAuditRecord
    used_deterministic_fallback: bool


class LegalPravnikAgentService:
    def __init__(self, llm: BaseLLMProvider, *, cfg: PravnikRunConfig | None = None) -> None:
        self._llm = llm
        self._cfg = cfg or PravnikRunConfig()

    def _invoke_structured_safe(self, system_prompt: str, user_message: str) -> AgentPravnikRuOutput:
        try:
            return self._llm.invoke_structured(system_prompt, user_message, AgentPravnikRuOutput)
        except ValidationError as e:
            raise PravnikValidationError(str(e)) from e
        except Exception as e:
            raise PravnikInvocationError(str(e)) from e

    def run(self, inp: AgentPravnikRuInput) -> AgentPravnikRunResult:
        if inp.jurisdiction != "Russia":
            raise PravnikInputError("agent_pravnik MVP supports only jurisdiction='Russia'.")
        case_fp = fingerprint_case_id(inp.case_id)
        started = now_iso()
        bridge = _bridge_legal_strategy_input(inp)
        prov_n = len(allowed_provision_keys(bridge))

        repair_count = 0
        used_fallback = False
        user_msg = build_user_message(inp)
        last_contract: list[str] = []
        last_quality: list[str] = []

        out: AgentPravnikRuOutput | None = None
        for attempt in range(_MAX_ATTEMPTS):
            if attempt == 0:
                um = user_msg
            else:
                um = user_msg + "\n\n" + build_repair_addon_ru(last_contract, last_quality)

            try:
                candidate = self._invoke_structured_safe(SYSTEM_PRAVNIK_RU, um)
            except (PravnikInvocationError, PravnikValidationError) as e:
                log.warning("agent_pravnik_invoke_failed case_id_fp=%s attempt=%s err=%s", case_fp, attempt + 1, e)
                last_contract = []
                last_quality = [f"llm_invoke_failed: {e}"]
                if attempt == _MAX_ATTEMPTS - 1:
                    emit_fallback(case_fp)
                    out = build_deterministic_fallback(inp)
                    used_fallback = True
                    break
                repair_count += 1
                continue

            last_contract = pravnik_contract_violations(inp, candidate)
            last_quality = quality_gate_violations(inp, candidate)
            # Plan §13.5 — Russian draft heuristic
            if not last_quality and cyrillic_ratio(candidate.legal_argument_section) < 0.12:
                last_quality = ["legal_argument_section: insufficient Cyrillic for Russian litigation draft"]

            if not last_contract and not last_quality:
                out = candidate
                break

            emit_draft_rejected(case_fp, last_contract + last_quality)
            log.warning(
                "agent_pravnik_draft_rejected case_id_fp=%s attempt=%s contract=%s quality=%s",
                case_fp,
                attempt + 1,
                last_contract,
                last_quality,
            )
            if attempt < _MAX_ATTEMPTS - 1:
                repair_count += 1
                continue

            emit_fallback(case_fp)
            out = build_deterministic_fallback(inp)
            used_fallback = True
            break

        if out is None:
            emit_fallback(case_fp)
            out = build_deterministic_fallback(inp)
            used_fallback = True

        final_contract_violations = pravnik_contract_violations(inp, out)
        if not used_fallback and final_contract_violations:
            log.error(
                "agent_pravnik_contract_invariant_broken case_id_fp=%s violations=%s",
                case_fp,
                final_contract_violations,
            )
            emit_fallback(case_fp)
            out = build_deterministic_fallback(inp)
            used_fallback = True
            final_contract_violations = pravnik_contract_violations(inp, out)

        if "no_new_articles_added" not in out.grounding_manifest.flags:
            out.grounding_manifest.flags.append("no_new_articles_added")

        finished = now_iso()
        final_quality = quality_gate_violations(inp, out)
        audit = PravnikAuditRecord(
            case_id_fp=case_fp,
            jurisdiction=inp.jurisdiction,
            prompt_version=self._cfg.prompt_version,
            schema_version=out.schema_version or PRAVNIK_SCHEMA_VERSION,
            model_name=self._cfg.model_name,
            document_kind=inp.document_kind,
            work_mode=inp.work_mode,
            repair_count=repair_count,
            contract_ok=not bool(final_contract_violations),
            contract_violation_count=len(final_contract_violations),
            quality_ok=not bool(final_quality) and cyrillic_ratio(out.legal_argument_section) >= 0.12,
            used_deterministic_fallback=used_fallback,
            started_at_iso=started,
            finished_at_iso=finished,
            error_code=None,
            input_summary=PravnikAuditRecord.build_input_summary(
                facts_n=len(inp.facts),
                flags_n=len(inp.issue_flags),
                provisions_n=prov_n,
                summary_len=len(inp.cleaned_summary),
            ),
        )
        emit_audit_log(audit)
        return AgentPravnikRunResult(output=out, audit=audit, used_deterministic_fallback=used_fallback)
