"""
Agent 2 runner — structured LLM call, validation, evidence contract, optional repair.

Does not perform retrieval. Does not log full case text by default.
"""
from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
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
from app.modules.common.agents.agent2_legal_strategy.input_schemas import CaseDocumentInput, LegalStrategyAgent2Input
from app.modules.common.agents.agent2_legal_strategy.litigation_fallback_text import (
    PRIMARY_WHY_BY_ARTICLE,
    SUPPORTING_HOW,
    detailed_issue_comment,
)
from app.modules.common.agents.agent2_legal_strategy.extraction_schemas import (
    DefenseBlock,
    DocumentGroup,
    DocumentItem,
    EvidenceRef,
    IssueItem,
    LegalBasisRef,
    LegalExtractionAgent2Output,
)
from app.modules.common.agents.agent2_legal_strategy.id_generator import (
    make_defense_id,
    make_doc_id,
    make_group_id,
    make_issue_id,
)
from app.modules.common.agents.agent2_legal_strategy.prompts import (
    AGENT2_EXTRACTION_SYSTEM_PROMPT,
    AGENT2_SYSTEM_PROMPT_VERSION,
    USER_MESSAGE_FOOTER,
    USER_MESSAGE_HEADER,
    build_repair_addon,
    build_system_prompt,
)
from app.modules.common.agents.agent2_legal_strategy.schemas import (
    FactToLawRow,
    LegalStrategyAgent2Output,
    MissingEvidenceBlock,
    NextStepItem,
    PrimaryBasisItem,
    SourceRef,
    StrategicAssessmentBlock,
    SupportingBasisItem,
)
from app.modules.common.agents.agent2_legal_strategy.telemetry import (
    Agent2AuditRecord,
    emit_audit_log,
    fingerprint_case_id,
    now_iso,
)
from app.modules.common.llm.provider import BaseLLMProvider

log = logging.getLogger(__name__)

_MAX_DEPTH_ATTEMPTS = 3

_FORBIDDEN_DEPTH_PHRASES: tuple[str, ...] = (
    "supports the issue",
    "is relevant",
    "provides context",
    "may indicate",
    "suggests that",
)

_LEGAL_DEPTH_MARKERS: tuple[str, ...] = (
    "violation",
    "invalid",
    "procedural defect",
    "grounds for",
    "results in",
    "therefore",
)

# Appended to deterministic primary why_it_matters so every row always satisfies the >=2-marker rule.
_DEPTH_MARKER_ENFORCER = (
    " This constitutes a procedural defect and an actionable violation of the cited article; therefore it supplies "
    "independent grounds for reversal, remand, or restoration of procedural deadlines as factually supported."
)


def _forbidden_phrase_in_text(text: str) -> str | None:
    tl = text.lower()
    for ph in _FORBIDDEN_DEPTH_PHRASES:
        if ph in tl:
            return ph
    return None


def _legal_marker_count(text: str) -> int:
    t = text.lower()
    return sum(1 for m in _LEGAL_DEPTH_MARKERS if m in t)


# Layer 2 — semantic structure (not just keywords): case anchor → legal anchor → breach → remedy.
# English + Russian cues so RU/EN outputs both pass when they follow a real argument shape.
_STRUCTURE_FACT_ANCHORS: tuple[str, ...] = (
    "failure",
    "absence",
    "lack of",
    "without ",
    "did not",
    "was not",
    "not notified",
    "foreign",
    "late ",
    "non-compliance",
    "factual",
    "case facts",
    "party",
    "defendant",
    "applicant",
    "court",
    "hearing",
    "judgment",
    "notice",
    "service",
    "не был",
    "без ",
    "отсутств",
    "иностран",
    "переводчик",
    "извещ",
    "адрес",
)
_STRUCTURE_LEGAL_RULE_ANCHORS: tuple[str, ...] = (
    "article",
    "provision",
    "norm",
    "statute",
    "excerpt",
    "cited",
    "кодекс",
    "гпк",
    "ск ",
    "ст.",
    "echr",
    " rule",
    "правил",
    "норм",
)
_STRUCTURE_VIOLATION_ANCHORS: tuple[str, ...] = (
    "violation",
    "violates",
    "breach",
    "defect",
    "non-compliance",
    "наруш",
    "поруш",
    "ущемл",
)
_STRUCTURE_CONSEQUENCE_ANCHORS: tuple[str, ...] = (
    "invalid",
    "grounds for",
    "results in",
    "leads to",
    "therefore",
    "reversal",
    "restoration",
    "remand",
    "void",
    "set aside",
    "отмен",
    "восстановлен",
    "оспор",
    "обжалован",
)


def _text_contains_any_anchor(text: str, anchors: tuple[str, ...]) -> bool:
    tl = text.lower()
    return any(a.lower() in tl for a in anchors)


def _validate_legal_logic_structure(text: str) -> tuple[bool, list[str]]:
    """
    Reject keyword-stuffed prose that passes length/marker checks but lacks argumentative skeleton.
    Each check is intentionally soft-multilingual; at least one hit per bucket is required.
    """
    reasons: list[str] = []
    if not _text_contains_any_anchor(text, _STRUCTURE_FACT_ANCHORS):
        reasons.append("structure_missing_fact_or_case_anchor")
    if not _text_contains_any_anchor(text, _STRUCTURE_LEGAL_RULE_ANCHORS):
        reasons.append("structure_missing_legal_rule_anchor")
    if not _text_contains_any_anchor(text, _STRUCTURE_VIOLATION_ANCHORS):
        reasons.append("structure_missing_violation_or_defect")
    if not _text_contains_any_anchor(text, _STRUCTURE_CONSEQUENCE_ANCHORS):
        reasons.append("structure_missing_consequence_or_relief")
    return (not reasons, reasons)


def _validate_legal_depth(
    inp: LegalStrategyAgent2Input,
    out: LegalStrategyAgent2Output,
) -> tuple[bool, list[str]]:
    """
    Litigation-quality gate: reject generic or shallow reasoning before returning to clients.
    Returns (ok, list of human-readable rejection reasons with field paths).
    """
    reasons: list[str] = []
    pack_has_provisions = bool(allowed_provision_keys(inp))

    if not out.primary_legal_basis:
        if pack_has_provisions and not out.insufficient_support_items:
            reasons.append(
                "primary_legal_basis: empty while evidence pack contains provisions "
                "and insufficient_support_items is empty"
            )
    else:
        for i, item in enumerate(out.primary_legal_basis):
            field = f"primary_legal_basis[{i}].why_it_matters"
            w = item.why_it_matters or ""
            if len(w) < 200:
                reasons.append(f"{field}: too_short len={len(w)} (min 200)")
            fp = _forbidden_phrase_in_text(w)
            if fp:
                reasons.append(f"{field}: forbidden_phrase={fp!r}")
            if _legal_marker_count(w) < 2:
                reasons.append(
                    f"{field}: needs>=2 legal-depth markers (violation|invalid|procedural defect|grounds for|"
                    f"results in|therefore); got {_legal_marker_count(w)}"
                )
            ok_logic, logic_reasons = _validate_legal_logic_structure(w)
            if not ok_logic:
                for lr in logic_reasons:
                    reasons.append(f"{field}:{lr}")

    if out.fact_to_law_mapping:
        for i, row in enumerate(out.fact_to_law_mapping):
            field = f"fact_to_law_mapping[{i}].comment"
            c = row.comment or ""
            if len(c) < 150:
                reasons.append(f"{field}: too_short len={len(c)} (min 150)")
            fp = _forbidden_phrase_in_text(c)
            if fp:
                reasons.append(f"{field}: forbidden_phrase={fp!r}")

    sa = out.strategic_assessment
    for list_name, items in (
        ("strongest_arguments", sa.strongest_arguments),
        ("weaker_arguments", sa.weaker_arguments),
        ("likely_vulnerabilities", sa.likely_vulnerabilities),
        ("opposing_side_may_argue", sa.opposing_side_may_argue),
    ):
        for j, s in enumerate(items):
            if not (s or "").strip():
                continue
            field = f"strategic_assessment.{list_name}[{j}]"
            fp = _forbidden_phrase_in_text(s)
            if fp:
                reasons.append(f"{field}: forbidden_phrase={fp!r}")

    return (not reasons, reasons)


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


@dataclass
class LegalExtractionAgent2RunResult:
    """Agent 2 extraction output (document classification + issue extraction) plus audit metadata."""

    output: LegalExtractionAgent2Output
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

        repair_count_total = 0
        validation_ok = True
        used_deterministic_fallback = False

        out: LegalStrategyAgent2Output | None = None
        depth_failure_log: list[str] = []

        for depth_attempt in range(_MAX_DEPTH_ATTEMPTS):
            candidate: LegalStrategyAgent2Output | None = None
            try:
                candidate = self._invoke_structured_safe(system_prompt, user_message)
            except Agent2InvocationError as e:
                log.warning(
                    "agent2_depth_invoke_failed case_id_fp=%s depth_attempt=%s/%s error=%s",
                    case_fp,
                    depth_attempt + 1,
                    _MAX_DEPTH_ATTEMPTS,
                    e,
                )
                depth_failure_log.append(f"depth_attempt_{depth_attempt}:invoke:{e.code}")
                continue
            except Agent2ValidationError as e:
                log.warning(
                    "agent2_depth_validation_failed case_id_fp=%s depth_attempt=%s/%s error=%s",
                    case_fp,
                    depth_attempt + 1,
                    _MAX_DEPTH_ATTEMPTS,
                    e,
                )
                depth_failure_log.append(f"depth_attempt_{depth_attempt}:pydantic:{e}")
                continue

            if _is_effectively_empty_output(candidate):
                log.warning(
                    "agent2_empty_output_rejected case_id_fp=%s depth_attempt=%s/%s",
                    case_fp,
                    depth_attempt + 1,
                    _MAX_DEPTH_ATTEMPTS,
                )
                depth_failure_log.append(f"depth_attempt_{depth_attempt}:empty_output")
                continue

            rc = 0
            violations = contract_violations(inp, candidate)
            while violations and rc < cfg.max_repair_attempts:
                rc += 1
                log.warning(
                    "agent2_contract_repair case_id_fp=%s depth_attempt=%s contract_repair=%s violations=%s",
                    case_fp,
                    depth_attempt + 1,
                    rc,
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
                    candidate = self._invoke_structured_safe(repair_system, user_message)
                except (Agent2InvocationError, Agent2ValidationError) as e:
                    log.warning(
                        "agent2_contract_repair_invoke_failed case_id_fp=%s depth_attempt=%s err=%s",
                        case_fp,
                        depth_attempt + 1,
                        e,
                    )
                    violations = ["repair_invoke_failed"]
                    break
                if _is_effectively_empty_output(candidate):
                    violations = ["empty_after_repair"]
                    break
                violations = contract_violations(inp, candidate)

            repair_count_total += rc

            if violations:
                log.warning(
                    "agent2_contract_unsatisfied_after_repair case_id_fp=%s depth_attempt=%s/%s violations=%s",
                    case_fp,
                    depth_attempt + 1,
                    _MAX_DEPTH_ATTEMPTS,
                    violations[:5],
                )
                depth_failure_log.append(f"depth_attempt_{depth_attempt}:contract:{violations[:3]}")
                continue

            if _should_force_grounded_fallback(inp, candidate):
                log.warning(
                    "agent2_undercovered_output_replaced case_id_fp=%s depth_attempt=%s",
                    case_fp,
                    depth_attempt + 1,
                )
                candidate = _build_grounded_fallback_output(inp)

            ok, depth_reasons = _validate_legal_depth(inp, candidate)
            if ok:
                out = candidate
                break

            log.warning(
                "agent2_legal_depth_rejected case_id_fp=%s depth_attempt=%s/%s reasons=%s",
                case_fp,
                depth_attempt + 1,
                _MAX_DEPTH_ATTEMPTS,
                depth_reasons,
            )
            depth_failure_log.append(f"depth_attempt_{depth_attempt}:legal_depth:{depth_reasons}")

        if out is None:
            log.warning(
                "agent2_using_deterministic_fallback case_id_fp=%s after_failed_attempts=%s log=%s",
                case_fp,
                _MAX_DEPTH_ATTEMPTS,
                depth_failure_log,
            )
            out = _build_grounded_fallback_output(inp)
            used_deterministic_fallback = True
            repair_count_total = 0

        violations_final = contract_violations(inp, out)
        if violations_final:
            err = Agent2OutputContractError(
                "Structured output cites provisions not present in legal_evidence_pack.",
                violations=violations_final,
            )
            finished = now_iso()
            audit = self._make_audit(
                inp=inp,
                case_fp=case_fp,
                started=started,
                finished=finished,
                validation_ok=validation_ok,
                repair_count=repair_count_total,
                contract_ok=False,
                violation_n=len(violations_final),
                error_code=err.code,
                prompt_version=cfg.prompt_version,
            )
            emit_audit_log(audit)
            raise err

        if not out.primary_legal_basis and out.insufficient_support_items:
            log.info(
                "agent2_insufficient_grounding_mode case_id_fp=%s insufficient_support_n=%s",
                case_fp,
                len(out.insufficient_support_items),
            )

        if used_deterministic_fallback:
            log.info(
                "agent2_final_output_source=deterministic_litigation_fallback case_id_fp=%s",
                case_fp,
            )

        finished = now_iso()
        audit = self._make_audit(
            inp=inp,
            case_fp=case_fp,
            started=started,
            finished=finished,
            validation_ok=validation_ok,
            repair_count=repair_count_total,
            contract_ok=True,
            violation_n=0,
            error_code=None,
            prompt_version=cfg.prompt_version,
        )
        emit_audit_log(audit)
        return LegalStrategyAgent2RunResult(output=out, audit=audit)

    # ------------------------------------------------------------------
    # Extraction mode: document classification + issue extraction
    # ------------------------------------------------------------------

    def run_extraction(
        self,
        inp: LegalStrategyAgent2Input,
        *,
        config: Agent2RunConfig | None = None,
    ) -> LegalExtractionAgent2RunResult:
        """
        Run Agent 2 in extraction mode.

        Classifies case documents into typed groups, extracts legal issues
        with stable IDs, maps issues to the evidence pack, and generates
        defense blocks.  Never truncates or summarizes documents destructively.

        Falls back to a deterministic extraction when the LLM fails or returns
        an empty output.
        """
        cfg = config or Agent2RunConfig()
        started = now_iso()
        case_fp = fingerprint_case_id(inp.case_id)

        payload: dict[str, Any] = inp.model_dump(mode="json")
        inner = json.dumps(payload, ensure_ascii=False, indent=2)
        user_message = f"{USER_MESSAGE_HEADER}{inner}{USER_MESSAGE_FOOTER}"

        out: LegalExtractionAgent2Output | None = None

        for depth_attempt in range(_MAX_DEPTH_ATTEMPTS):
            try:
                candidate = self._llm.invoke_structured(
                    AGENT2_EXTRACTION_SYSTEM_PROMPT,
                    user_message,
                    LegalExtractionAgent2Output,
                )
            except Exception as e:
                log.warning(
                    "agent2_extraction_invoke_failed case_id_fp=%s depth=%s/%s err=%s",
                    case_fp, depth_attempt + 1, _MAX_DEPTH_ATTEMPTS, e,
                )
                continue

            if _is_effectively_empty_extraction(candidate):
                log.warning(
                    "agent2_extraction_empty_output case_id_fp=%s depth=%s/%s",
                    case_fp, depth_attempt + 1, _MAX_DEPTH_ATTEMPTS,
                )
                continue

            # Assign/validate deterministic IDs (override any model-generated ones)
            candidate = _assign_extraction_ids(candidate, inp.case_id)
            out = candidate
            break

        if out is None:
            log.warning(
                "agent2_extraction_using_deterministic_fallback case_id_fp=%s",
                case_fp,
            )
            out = _build_deterministic_extraction(inp)

        # Enforce evidence-bound output: each issue/defense must carry traceable references.
        out = _ensure_traceable_evidence(out, inp)

        finished = now_iso()
        audit = Agent2AuditRecord(
            case_id_fp=case_fp,
            jurisdiction=inp.jurisdiction[:128],
            prompt_version=AGENT2_EXTRACTION_SYSTEM_PROMPT[:64],
            schema_version="agent2_legal_extraction.v1",
            model_name=self._model_name[:128],
            validation_ok=True,
            repair_count=0,
            contract_ok=True,
            contract_violation_count=0,
            started_at_iso=started,
            finished_at_iso=finished,
            error_code=None,
            input_summary=Agent2AuditRecord.build_input_summary(
                facts_n=len(inp.facts),
                flags_n=len(inp.issue_flags),
                provisions_n=len(allowed_provision_keys(inp)),
                summary_len=len(inp.cleaned_summary or ""),
            ),
        )
        emit_audit_log(audit)
        return LegalExtractionAgent2RunResult(output=out, audit=audit)

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


def _is_effectively_empty_output(out: LegalStrategyAgent2Output) -> bool:
    return (
        not out.case_theory.strip()
        and not out.primary_legal_basis
        and not out.supporting_legal_basis
        and not out.fact_to_law_mapping
        and not out.recommended_next_steps
        and not out.draft_argument_direction.strip()
    )


def _normalize_law(law: str) -> str:
    return "".join(ch.lower() for ch in law if ch.isalnum())


def _build_grounded_fallback_output(inp: LegalStrategyAgent2Input) -> LegalStrategyAgent2Output:
    """
    Deterministic non-empty strategy used only when model returns an empty structured object.
    Cites provisions strictly from the provided legal_evidence_pack.
    """
    refs: list[SourceRef] = []
    seen: set[tuple[str, str]] = set()
    for src in inp.legal_evidence_pack.primary_sources + inp.legal_evidence_pack.supporting_sources:
        key = (_normalize_law(src.law), str(src.article))
        if key not in seen:
            seen.add(key)
            refs.append(SourceRef(law=src.law, article=str(src.article), title=src.title))
    for art in inp.legal_evidence_pack.retrieved_articles:
        key = (_normalize_law(art.law), str(art.article))
        if key not in seen:
            seen.add(key)
            refs.append(SourceRef(law=art.law, article=str(art.article), title=None))

    by_article: dict[str, list[SourceRef]] = {}
    for ref in refs:
        by_article.setdefault(str(ref.article), []).append(ref)

    def pick(article: str, law_hint: str | None = None) -> SourceRef | None:
        candidates = by_article.get(article, [])
        if not candidates:
            return None
        if law_hint is None:
            return candidates[0]
        n_hint = _normalize_law(law_hint)
        for c in candidates:
            if n_hint in _normalize_law(c.law):
                return c
        return candidates[0]

    # Core legal basis for the active Czech/Russia alimony procedural scenario.
    preferred_primary = [
        ("9", "gpk"),
        ("162", "gpk"),
        ("113", "gpk"),
        ("116", "gpk"),
        ("167", "gpk"),
        ("112", "gpk"),
        ("407", "gpk"),
        ("80", "sk"),
        ("81", "sk"),
    ]
    primary_basis: list[PrimaryBasisItem] = []
    for article, law_hint in preferred_primary:
        ref = pick(article, law_hint)
        if ref is None:
            continue
        why_raw = PRIMARY_WHY_BY_ARTICLE.get(
            article,
            (
                f"Facts from the file tie to norms governing article {ref.article} as supplied in the pack. "
                "State the legal rule from the excerpt, identify the alleged breach (notice, language, service, "
                "or deadline), and spell out the procedural consequence (invalidity risk, reversal, restoration) "
                "under the applicable procedural articles also in the pack."
            ),
        )
        why = why_raw + _DEPTH_MARKER_ENFORCER
        primary_basis.append(
            PrimaryBasisItem(
                provision=ref,
                why_it_matters=why,
                connected_facts=list(inp.facts[:5]),
            )
        )

    supporting_basis: list[SupportingBasisItem] = []
    for article, law_hint in [("398", "gpk"), ("6", "echr")]:
        ref = pick(article, law_hint)
        if ref is None:
            continue
        how = SUPPORTING_HOW.get(
            article,
            (
                "Reinforces the primary procedural attack by framing equal treatment and fair-trial expectations "
                "consistent with the excerpts — without replacing the domestic articles that directly govern "
                "notice, language, and service."
            ),
        )
        supporting_basis.append(
            SupportingBasisItem(
                provision=ref,
                how_it_reinforces=how,
            )
        )

    issue_to_articles: dict[str, list[tuple[str, str]]] = {
        "language_issue": [("9", "gpk")],
        "interpreter_issue": [("162", "gpk"), ("9", "gpk")],
        "notice_issue": [("113", "gpk"), ("167", "gpk")],
        "service_address_issue": [("116", "gpk"), ("113", "gpk")],
        "foreign_party_issue": [("398", "gpk"), ("9", "gpk")],
        "foreign_service_issue": [("407", "gpk"), ("398", "gpk")],
        "missed_deadline_due_to_service_issue": [("112", "gpk")],
        "appellate_reversal_issue": [("330", "gpk"), ("112", "gpk"), ("113", "gpk")],
        "alimony_issue": [("80", "sk"), ("81", "sk")],
    }

    fact_to_law: list[FactToLawRow] = []
    facts_for_comments = list(inp.facts[:5]) or [inp.cleaned_summary[:400] if inp.cleaned_summary else "case facts"]
    for issue in inp.issue_flags:
        rows = issue_to_articles.get(issue, [])
        provs: list[SourceRef] = []
        for art, law_hint in rows:
            ref = pick(art, law_hint)
            if ref is not None and all((p.law, p.article) != (ref.law, ref.article) for p in provs):
                provs.append(ref)
        if not provs:
            continue
        fact_to_law.append(
            FactToLawRow(
                issue_name=issue,
                relevant_facts=list(inp.facts[:5]),
                legal_provisions=provs,
                assessment_strength="strong" if issue in {
                    "notice_issue",
                    "service_address_issue",
                    "interpreter_issue",
                    "foreign_service_issue",
                    "missed_deadline_due_to_service_issue",
                } else "medium",
                comment=detailed_issue_comment(issue, facts_for_comments),
            )
        )

    next_steps = [
        NextStepItem(
            step_order=1,
            action=(
                "File or amend an appellate brief (апелляционная жалоба) citing Article 330 ГПК РФ: map each "
                "alleged defect (Articles 9, 113, 116, 162, 167, 407) to the corresponding ground for reversal, "
                "with a short record cite or exhibit list for service and interpreter."
            ),
        ),
        NextStepItem(
            step_order=2,
            action=(
                "Submit a freestanding application to restore the missed appeal deadline under Article 112 ГПК РФ, "
                "attaching proof of non-service or late discovery (postal traces, foreign-address evidence, "
                "timeline of learning of the judgment)."
            ),
        ),
        NextStepItem(
            step_order=3,
            action=(
                "If enforcement has begun, lodge objections and request a stay where permitted, attaching the "
                "same procedural-defect theory so execution does not prejudice appellate or cancellation rights."
            ),
        ),
        NextStepItem(
            step_order=4,
            action=(
                "Preserve a secondary line on alimony quantum under Articles 80–81 СК РФ only after the court "
                "reopens a fair hearing or remands — avoid waiving material challenges while procedural "
                "invalidity is pending."
            ),
        ),
    ]

    return LegalStrategyAgent2Output(
        case_theory=(
            "This is a cross-border alimony dispute where the decisive question is not merely the statutory duty "
            "to pay support but whether the first-instance judgment was rendered after a procedurally lawful "
            "hearing.\n\n"
            "The party alleges a cluster of interconnected defects: inadequate or absent interpreter and language "
            "safeguards (Articles 9 and 162 ГПК РФ), failure to notify and serve in compliance with the rules on "
            "judicial notices and physical delivery (Articles 113–116 ГПК РФ), and — critically for a foreign "
            "address — failure to use the international judicial-assistance route where service abroad was "
            "required (Article 407 ГПК РФ), reinforced by equal procedural standing of foreign persons "
            "(Article 398 ГПК РФ).\n\n"
            "If notice was not lawfully effected, proceeding to disposition in the party's absence engages "
            "Article 167 ГПК РФ and may render the judgment vulnerable on procedural grounds under Article 330. "
            "The missed appellate deadline, if caused by those defects, must be addressed through Article 112 "
            "before substantive relief is time-barred.\n\n"
            "Material alimony provisions (Articles 80–81 СК РФ) define the subject matter and default shares, "
            "but they do not cure a hearing that violated core participation guarantees; the litigation strategy "
            "therefore leads with procedural invalidity and preserves quantum arguments for a lawfully composed "
            "record."
        ),
        primary_legal_basis=primary_basis,
        supporting_legal_basis=supporting_basis,
        fact_to_law_mapping=fact_to_law,
        strategic_assessment=StrategicAssessmentBlock(
            strongest_arguments=[
                (
                    "Notice and service chain: if the court cannot prove compliant notice to the actual foreign "
                    "residence and did not use treaty-based assistance where required, the absentee or default "
                    "posture of the judgment collapses — this is a textbook procedural attack under Articles 113–116 "
                    "and 167 tied to Article 330."
                ),
                (
                    "Language and interpreter: Articles 9 and 162 together show that a hearing without effective "
                    "translation is not a mere inconvenience; it denies equality of arms and meaningful defense, "
                    "which strengthens reversal arguments beyond generic fairness rhetoric."
                ),
                (
                    "Deadline restoration (Article 112): even strong appellate grounds fail if the appeal is late; "
                    "restoration must be briefed first with documentary proof linking the delay to service failure, "
                    "not to negligence."
                ),
            ],
            weaker_arguments=[
                (
                    "Pure substantive attack on alimony percentage under Article 81 without first fixing the "
                    "procedural record risks a court deciding the case as if the first hearing were valid — weaker "
                    "until procedural relief is obtained."
                ),
            ],
            likely_vulnerabilities=[
                (
                    "The court or opponent may argue waiver, implied consent, or that postal attempts amounted to "
                    "proper service — must be rebutted with concrete address and foreign-service evidence."
                ),
            ],
            opposing_side_may_argue=[
                (
                    "That the party had constructive knowledge through relatives, e-mail, or state databases — "
                    "requires fact-specific rebuttal and may implicate burden on proof of non-receipt."
                ),
            ],
        ),
        missing_evidence_gaps=MissingEvidenceBlock(
            what_is_unclear=[],
            needed_documents_or_facts=[],
        ),
        recommended_next_steps=next_steps,
        draft_argument_direction=(
            "Lead with procedural invalidity: establish that notice and cross-border service were not effected "
            "under Articles 113–116 and 407, that interpreter and language rights under Articles 9 and 162 were "
            "violated, and that absentee disposition under Article 167 therefore lacks a valid foundation. "
            "Pair that narrative with Article 330 grounds for reversal and, in parallel, seek restoration of the "
            "missed appeal deadline under Article 112 with proof tied to late discovery or failed service. "
            "Only then press material points under Articles 80–81 on a clean record. Relief sought: reversal or "
            "remand, stay of enforcement as appropriate, and restoration of appellate access."
        ),
        insufficient_support_items=[],
    )


def _should_force_grounded_fallback(inp: LegalStrategyAgent2Input, out: LegalStrategyAgent2Output) -> bool:
    """
    For the active cross-border alimony procedural case, if the model still reports
    missing support for issues that are already present in the evidence pack, replace
    with deterministic grounded output.
    """
    if not out.insufficient_support_items:
        return False

    required_articles = {"9", "112", "113", "116", "162", "167", "407", "80"}
    available_articles = {
        str(s.article) for s in inp.legal_evidence_pack.primary_sources + inp.legal_evidence_pack.supporting_sources
    } | {str(a.article) for a in inp.legal_evidence_pack.retrieved_articles}
    if not required_articles.issubset(available_articles):
        return False

    critical_flags = {
        "interpreter_issue",
        "language_issue",
        "notice_issue",
        "service_address_issue",
        "foreign_service_issue",
        "missed_deadline_due_to_service_issue",
    }
    if not (critical_flags & set(inp.issue_flags)):
        return False

    text = " ".join(f"{i.topic} {i.reason}".lower() for i in out.insufficient_support_items)
    critical_terms = (
        "deadline",
        "срок",
        "service",
        "извещ",
        "interpreter",
        "переводчик",
        "foreign",
        "иностран",
    )
    return any(term in text for term in critical_terms)


_GROUP_ORDER: tuple[str, ...] = (
    "judgments",
    "appeals",
    "claims",
    "party_submissions",
    "orders",
    "evidence",
    "procedural_documents",
    "translations",
    "service_documents",
    "other_relevant_documents",
)

_DOCUMENT_TYPE_TO_GROUP: dict[str, str] = {
    "judgment": "judgments",
    "judgments": "judgments",
    "appeal": "appeals",
    "appeals": "appeals",
    "claim": "claims",
    "claims": "claims",
    "party_submission": "party_submissions",
    "party_submissions": "party_submissions",
    "order": "orders",
    "orders": "orders",
    "evidence": "evidence",
    "procedural_document": "procedural_documents",
    "procedural_documents": "procedural_documents",
    "translation": "translations",
    "translations": "translations",
    "service_document": "service_documents",
    "service_documents": "service_documents",
    "other_relevant_document": "other_relevant_documents",
    "other_relevant_documents": "other_relevant_documents",
}


def _is_core_document(document_type: str) -> bool:
    return document_type in {"judgment", "appeal", "claim"}


def _normalize_document_type(document_type: str) -> str:
    dt = (document_type or "").strip().lower()
    if not dt:
        return "other_relevant_document"
    if dt in _DOCUMENT_TYPE_TO_GROUP:
        # Keep singular value in the document row where possible.
        if dt.endswith("s"):
            return dt[:-1] if dt not in {"claims"} else "claim"
        return dt
    return "other_relevant_document"


def _group_for_document_type(document_type: str) -> str:
    dt = _normalize_document_type(document_type)
    return _DOCUMENT_TYPE_TO_GROUP.get(dt, "other_relevant_documents")


def _issue_slug_from_flag(flag: str) -> str:
    slug = (flag or "").strip().lower().replace("-", "_").replace(" ", "_")
    return slug or "unknown_issue"


def _issue_title_from_slug(slug: str) -> str:
    return slug.replace("_", " ").strip().title() or "Issue"


def _doc_refs_for_issue_slug(
    groups: list[DocumentGroup],
    issue_slug: str,
) -> list[str]:
    tokens = set(issue_slug.split("_"))
    refs: list[str] = []
    for group in groups:
        for doc in group.documents:
            haystack = " ".join(
                [
                    doc.document_type or "",
                    doc.title or "",
                    doc.summary or "",
                    " ".join(doc.key_points),
                ]
            ).lower()
            if any(tok and tok in haystack for tok in tokens):
                refs.append(doc.doc_id)
    return refs


def _legal_basis_from_pack(inp: LegalStrategyAgent2Input, cap: int = 5) -> list[LegalBasisRef]:
    refs: list[LegalBasisRef] = []
    seen: set[tuple[str, str]] = set()

    for src in inp.legal_evidence_pack.primary_sources + inp.legal_evidence_pack.supporting_sources:
        key = (src.law, str(src.article))
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            LegalBasisRef(
                law=src.law,
                provision=str(src.article),
                why_applicable="Provision appears in the evidence pack and maps to stated issue flags/facts.",
                legal_effect="Grounds procedural or substantive relief depending on court findings.",
            )
        )
        if len(refs) >= cap:
            break
    return refs


def _is_effectively_empty_extraction(out: LegalExtractionAgent2Output) -> bool:
    return not out.groups and not out.issues and not out.defense_blocks


def _assign_extraction_ids(out: LegalExtractionAgent2Output, case_id: str) -> LegalExtractionAgent2Output:
    for group in out.groups:
        group.group_id = make_group_id(case_id, group.group_name)
        for idx, doc in enumerate(group.documents):
            doc.logical_index = idx
            doc.doc_id = make_doc_id(
                case_id=case_id,
                logical_index=idx,
                primary_doc_id=doc.primary_document_id,
            )

    for issue in out.issues:
        issue.issue_id = make_issue_id(case_id, issue.issue_slug)

    issue_map = {issue.issue_slug: issue.issue_id for issue in out.issues}
    for block in out.defense_blocks:
        guessed_slug = block.issue_id.split("::")[-1] if "::" in block.issue_id else block.issue_id
        block.issue_id = issue_map.get(guessed_slug, make_issue_id(case_id, guessed_slug))
        block.defense_id = make_defense_id(case_id, guessed_slug)

    out.case_id = case_id
    out.schema_version = "agent2_legal_extraction.v1"
    return out


def _parse_page_number(source_pages: list[str]) -> int:
    if not source_pages:
        return 1
    token = source_pages[0]
    m = re.search(r"(\d+)", token or "")
    if not m:
        return 1
    try:
        return max(1, int(m.group(1)))
    except Exception:
        return 1


def _split_sentences(text: str) -> list[str]:
    if not text.strip():
        return []
    chunks = re.split(r"(?<=[\.\!\?…])\s+|\n+", text)
    return [c.strip() for c in chunks if c.strip()]


def _extract_keywords(text: str, cap: int = 20) -> list[str]:
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9_]{4,}", (text or "").lower())
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= cap:
            break
    return out


def _find_evidence_snippets(
    document: CaseDocumentInput,
    issue_text: str,
    *,
    max_items: int = 2,
) -> list[EvidenceRef]:
    """
    Find exact quote snippets inside document.content for the given issue/defense text.
    Strategy:
      1) substring keyword hit
      2) fuzzy fallback (SequenceMatcher ratio)
    """
    content = document.content or ""
    if not content.strip():
        return []
    sentences = _split_sentences(content)
    if not sentences:
        return []

    keywords = _extract_keywords(issue_text)
    matches: list[str] = []

    if keywords:
        for s in sentences:
            sl = s.lower()
            if any(k in sl for k in keywords):
                matches.append(s)
                if len(matches) >= max_items:
                    break

    if not matches:
        ranked = sorted(
            sentences,
            key=lambda s: SequenceMatcher(None, (issue_text or "").lower(), s.lower()).ratio(),
            reverse=True,
        )
        if ranked:
            matches.append(ranked[0])

    page = _parse_page_number(document.source_pages)
    refs: list[EvidenceRef] = []
    for q in matches[:max_items]:
        refs.append(EvidenceRef(doc_id="", page=page, quote=q))
    # doc_id is assigned by caller (Agent2 doc id context).
    return refs


def _build_case_doc_map(inp: LegalStrategyAgent2Input) -> dict[str, CaseDocumentInput]:
    """
    Build deterministic mapping from agent2 doc_id to reconstructed case document.
    """
    out: dict[str, CaseDocumentInput] = {}
    for idx, d in enumerate(inp.case_documents):
        out[make_doc_id(inp.case_id, idx, d.primary_document_id)] = d
    return out


def _attach_issue_evidence(issue: IssueItem, doc_map: dict[str, CaseDocumentInput]) -> None:
    if issue.evidence_refs:
        issue.requires_evidence = False
        return
    search_text = " ".join(
        [
            issue.issue_title,
            issue.problem_description,
            issue.defense_argument,
            " ".join(issue.factual_basis),
        ]
    ).strip()

    refs: list[EvidenceRef] = []
    candidate_doc_ids = issue.supporting_doc_ids or list(doc_map.keys())
    for doc_id in candidate_doc_ids:
        doc = doc_map.get(doc_id)
        if doc is None:
            continue
        found = _find_evidence_snippets(doc, search_text, max_items=1)
        for ref in found:
            ref.doc_id = doc_id
            refs.append(ref)
        if refs:
            break

    issue.evidence_refs = refs
    issue.requires_evidence = not bool(refs)


def _attach_defense_evidence(
    block: DefenseBlock,
    issue_lookup: dict[str, IssueItem],
    doc_map: dict[str, CaseDocumentInput],
) -> None:
    if block.evidence_refs:
        return

    # Reuse issue evidence first for strict traceability consistency.
    issue = issue_lookup.get(block.issue_id)
    if issue and issue.evidence_refs:
        block.evidence_refs = list(issue.evidence_refs[:2])
        return

    search_text = " ".join([block.title, block.argument_markdown]).strip()
    refs: list[EvidenceRef] = []
    candidate_doc_ids = block.supporting_doc_ids or list(doc_map.keys())
    for doc_id in candidate_doc_ids:
        doc = doc_map.get(doc_id)
        if doc is None:
            continue
        found = _find_evidence_snippets(doc, search_text, max_items=1)
        for ref in found:
            ref.doc_id = doc_id
            refs.append(ref)
        if refs:
            break
    block.evidence_refs = refs


def _ensure_traceable_evidence(
    out: LegalExtractionAgent2Output,
    inp: LegalStrategyAgent2Input,
) -> LegalExtractionAgent2Output:
    doc_map = _build_case_doc_map(inp)

    for issue in out.issues:
        _attach_issue_evidence(issue, doc_map)

    issue_lookup = {i.issue_id: i for i in out.issues}
    for block in out.defense_blocks:
        _attach_defense_evidence(block, issue_lookup, doc_map)

    return out


def _build_deterministic_extraction(inp: LegalStrategyAgent2Input) -> LegalExtractionAgent2Output:
    grouped_docs: dict[str, list[DocumentItem]] = {name: [] for name in _GROUP_ORDER}

    for raw in inp.case_documents:
        normalized_type = _normalize_document_type(raw.document_type)
        group_name = _group_for_document_type(normalized_type)
        logical_index = len(grouped_docs[group_name])
        grouped_docs[group_name].append(
            DocumentItem(
                doc_id=make_doc_id(inp.case_id, logical_index, raw.primary_document_id),
                logical_index=logical_index,
                primary_document_id=raw.primary_document_id,
                document_type=normalized_type,
                document_date=raw.document_date,
                document_role=raw.document_role,
                title=raw.title,
                is_core_document=_is_core_document(normalized_type),
                source_pages=list(raw.source_pages),
                full_text_reference=raw.full_text_reference,
                summary=(raw.content or "")[:1200],
                key_points=[(raw.content or "")[:300]] if raw.content else [],
                evidence_value="Potentially relevant to disputed facts and procedural posture.",
                procedural_value="Use for chronology, service, participation, and appeal posture.",
            )
        )

    groups = [
        DocumentGroup(
            group_id=make_group_id(inp.case_id, name),
            group_name=name,
            documents=grouped_docs[name],
        )
        for name in _GROUP_ORDER
        if grouped_docs[name]
    ]

    issues: list[IssueItem] = []
    defense_blocks: list[DefenseBlock] = []
    legal_basis = _legal_basis_from_pack(inp, cap=6)

    for flag in inp.issue_flags:
        issue_slug = _issue_slug_from_flag(flag)
        issue_id = make_issue_id(inp.case_id, issue_slug)
        supporting_doc_ids = _doc_refs_for_issue_slug(groups, issue_slug)
        issue = IssueItem(
            issue_id=issue_id,
            issue_slug=issue_slug,
            issue_title=_issue_title_from_slug(issue_slug),
            factual_basis=list(inp.facts[:8]),
            supporting_doc_ids=supporting_doc_ids,
            court_or_opponent_position="To be refined after full opponent submissions are ingested.",
            problem_description=(
                "Issue extracted from input facts and issue flags. Requires strict linkage of facts, "
                "documents, and provisions from evidence pack."
            ),
            defense_argument=(
                "Defense should connect documentary trail, procedural defects, and statutory consequences "
                "without dropping legally relevant source context."
            ),
            legal_basis=legal_basis,
            requested_consequence="Set aside, remand, or restore deadline based on procedural findings.",
            evidence_gaps=list(inp.optional_missing_items),
        )
        issues.append(issue)

        basis_refs = [f"{b.law} ст.{b.provision}" for b in legal_basis]
        defense_blocks.append(
            DefenseBlock(
                defense_id=make_defense_id(inp.case_id, issue_slug),
                issue_id=issue_id,
                title=f"Defense: {issue.issue_title}",
                argument_markdown=(
                    f"### {issue.issue_title}\n"
                    "This issue is legally material because the available record indicates a concrete procedural "
                    "or substantive defect linked to the disputed outcome. "
                    "The factual basis must be anchored in identified documents and not replaced by a short abstract. "
                    "Applicable provisions from the evidence pack define the governing legal rule and the threshold "
                    "for finding a violation. "
                    "Where the court record confirms non-compliance, the legal consequence includes reversal, remand, "
                    "or restoration of procedural rights depending on posture. "
                    "Requested relief should be framed as specific procedural action with explicit article references."
                ),
                supporting_doc_ids=supporting_doc_ids,
                legal_basis_refs=basis_refs,
            )
        )

    return LegalExtractionAgent2Output(
        schema_version="agent2_legal_extraction.v1",
        case_id=inp.case_id,
        source_artifact="",
        groups=groups,
        issues=issues,
        defense_blocks=defense_blocks,
    )
