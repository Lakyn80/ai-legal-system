"""
Grounding validators — reuse Agent 2 evidence_contract allowed set.
"""
from __future__ import annotations

from app.modules.common.agents.agent2_legal_strategy.evidence_contract import allowed_provision_keys
from app.modules.common.agents.agent2_legal_strategy.input_schemas import LegalStrategyAgent2Input
from app.modules.common.agents.agent2_legal_strategy.schemas import SourceRef

from app.modules.russia.agents.agent_pravnik.schemas import AgentPravnikRuInput, AgentPravnikRuOutput


def _norm(s: str) -> str:
    """Match evidence_contract._norm for (law, article) keys."""
    return " ".join(s.strip().lower().split())


def _bridge_legal_strategy_input(inp: AgentPravnikRuInput) -> LegalStrategyAgent2Input:
    """Same pack + case bundle shape as Agent 2 for allowed_provision_keys."""
    return LegalStrategyAgent2Input(
        case_id=inp.case_id,
        jurisdiction=inp.jurisdiction,
        cleaned_summary=inp.cleaned_summary,
        facts=inp.facts,
        timeline=inp.timeline,
        issue_flags=inp.issue_flags,
        claims_or_questions=inp.claims_or_questions,
        legal_evidence_pack=inp.legal_evidence_pack,
    )


def collect_grounding_manifest_keys(output: AgentPravnikRuOutput) -> list[tuple[str, str]]:
    """Normalized (law, article) pairs declared in grounding_manifest."""
    keys: list[tuple[str, str]] = []
    for p in output.grounding_manifest.cited_provisions:
        keys.append((_norm(p.law), _norm(p.article)))
    return keys


def pravnik_contract_violations(inp: AgentPravnikRuInput, output: AgentPravnikRuOutput) -> list[str]:
    """
    Return human-readable violations if grounding_manifest cites provisions not in the evidence pack.
    Empty list means contract satisfied for manifest (MVP: single source of truth per plan).
    """
    allowed = allowed_provision_keys(_bridge_legal_strategy_input(inp))
    bad: list[str] = []
    for law, art in collect_grounding_manifest_keys(output):
        if not allowed:
            bad.append(f"Cited provision but evidence pack has no provisions: {law!r} / {art!r}")
            continue
        if (law, art) not in allowed:
            bad.append(f"Cited provision not in evidence pack: {law!r} / {art!r}")
    return bad


def merge_manifest_with_agent2_primary(
    output: AgentPravnikRuOutput,
    *,
    agent2_refs: list[SourceRef],
) -> AgentPravnikRuOutput:
    """
    If model omitted manifest entries, union with primary basis from Agent 2 (still subset of pack).
    Used by fallback only — all refs come from agent2_output already validated.
    """
    seen = {(p.law.strip().lower(), p.article.strip().lower()) for p in output.grounding_manifest.cited_provisions}
    merged = list(output.grounding_manifest.cited_provisions)
    for p in agent2_refs:
        key = (p.law.strip().lower(), p.article.strip().lower())
        if key not in seen:
            merged.append(p)
            seen.add(key)
    output.grounding_manifest.cited_provisions = merged
    return output
