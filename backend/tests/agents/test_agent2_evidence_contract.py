"""Unit tests for evidence pack ↔ output contract checks."""
from __future__ import annotations

from app.modules.common.agents.agent2_legal_strategy.evidence_contract import (
    contract_violations,
    format_allowed_provisions_list,
)
from app.modules.common.agents.agent2_legal_strategy.input_schemas import (
    LegalEvidencePack,
    LegalStrategyAgent2Input,
)
from app.modules.common.agents.agent2_legal_strategy.schemas import (
    FactToLawRow,
    LegalStrategyAgent2Output,
    PrimaryBasisItem,
    SourceRef,
    StrategicAssessmentBlock,
)


def _inp() -> LegalStrategyAgent2Input:
    return LegalStrategyAgent2Input(
        case_id="x",
        jurisdiction="RU",
        legal_evidence_pack=LegalEvidencePack(
            primary_sources=[SourceRef(law="GPK RF", article="9")],
            supporting_sources=[],
            retrieved_articles=[],
        ),
    )


def test_contract_empty_when_output_matches_pack():
    inp = _inp()
    out = LegalStrategyAgent2Output(
        case_theory="t",
        primary_legal_basis=[
            PrimaryBasisItem(
                provision=SourceRef(law="GPK RF", article="9"),
                why_it_matters="m",
            )
        ],
        draft_argument_direction="d",
    )
    assert contract_violations(inp, out) == []


def test_contract_flags_unknown_article():
    inp = _inp()
    out = LegalStrategyAgent2Output(
        case_theory="t",
        primary_legal_basis=[
            PrimaryBasisItem(
                provision=SourceRef(law="GPK RF", article="999"),
                why_it_matters="m",
            )
        ],
        draft_argument_direction="d",
    )
    v = contract_violations(inp, out)
    assert len(v) == 1
    assert "999" in v[0] or "not in evidence" in v[0]


def test_fact_to_law_row_provisions_checked():
    inp = _inp()
    out = LegalStrategyAgent2Output(
        case_theory="t",
        fact_to_law_mapping=[
            FactToLawRow(
                issue_name="i",
                legal_provisions=[SourceRef(law="Other", article="1")],
                assessment_strength="weak",
                comment="c",
            )
        ],
        draft_argument_direction="d",
    )
    assert len(contract_violations(inp, out)) >= 1


def test_format_allowed_list_non_empty():
    inp = _inp()
    text = format_allowed_provisions_list(inp)
    assert "gpk" in text.lower() or "GPK" in text
