"""
Validate that structured output references only provisions present in the input evidence pack.
"""
from __future__ import annotations

from app.modules.common.agents.agent2_legal_strategy.input_schemas import LegalStrategyAgent2Input
from app.modules.common.agents.agent2_legal_strategy.schemas import LegalStrategyAgent2Output


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def allowed_provision_keys(inp: LegalStrategyAgent2Input) -> set[tuple[str, str]]:
    """Normalized (law, article) pairs allowed to appear in Agent 2 output citations."""
    pack = inp.legal_evidence_pack
    keys: set[tuple[str, str]] = set()
    for src in pack.primary_sources + pack.supporting_sources:
        keys.add((_norm(src.law), _norm(src.article)))
    for ra in pack.retrieved_articles:
        keys.add((_norm(ra.law), _norm(ra.article)))
    return keys


def format_allowed_provisions_list(inp: LegalStrategyAgent2Input) -> str:
    """Human-readable list for repair prompts (not logged verbatim in production audit by default)."""
    lines: list[str] = []
    for law, art in sorted(allowed_provision_keys(inp)):
        lines.append(f"- {law} / art. {art}")
    return "\n".join(lines) if lines else "(no provisions in pack — output must not invent citations)"


def collect_cited_keys(output: LegalStrategyAgent2Output) -> list[tuple[str, str]]:
    """All (law, article) pairs cited in the structured output."""
    found: list[tuple[str, str]] = []
    for item in output.primary_legal_basis:
        p = item.provision
        found.append((_norm(p.law), _norm(p.article)))
    for item in output.supporting_legal_basis:
        p = item.provision
        found.append((_norm(p.law), _norm(p.article)))
    for row in output.fact_to_law_mapping:
        for p in row.legal_provisions:
            found.append((_norm(p.law), _norm(p.article)))
    return found


def contract_violations(
    inp: LegalStrategyAgent2Input,
    output: LegalStrategyAgent2Output,
) -> list[str]:
    """
    Return human-readable violation lines for provisions cited but not in the input pack.
    Empty list means contract satisfied.
    """
    allowed = allowed_provision_keys(inp)
    if not allowed:
        # Pack empty: any cited provision is a violation (cannot invent law).
        allowed = set()

    bad: list[str] = []
    for law, art in collect_cited_keys(output):
        if (law, art) not in allowed:
            bad.append(f"Cited provision not in evidence pack: {law!r} / {art!r}")
    return bad
