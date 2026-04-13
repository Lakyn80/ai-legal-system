"""Tests for Agent 2 legal strategy service (mocked LLM)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.modules.common.agents.agent2_legal_strategy.errors import (
    Agent2InvocationError,
    Agent2OutputContractError,
)
from app.modules.common.agents.agent2_legal_strategy.input_schemas import (
    LegalEvidencePack,
    LegalStrategyAgent2Input,
)
from app.modules.common.agents.agent2_legal_strategy.prompts import USER_MESSAGE_HEADER
from app.modules.common.agents.agent2_legal_strategy.schemas import (
    InsufficientSupportItem,
    LegalStrategyAgent2Output,
    MissingEvidenceBlock,
    PrimaryBasisItem,
    SourceRef,
    StrategicAssessmentBlock,
)
from app.modules.common.agents.agent2_legal_strategy.service import Agent2RunConfig, LegalStrategyAgent2Service
from app.modules.common.llm.provider import BaseLLMProvider


def _gpk_pack() -> LegalEvidencePack:
    return LegalEvidencePack(
        primary_sources=[
            SourceRef(law="GPK RF", article="9", title="Language"),
            SourceRef(law="GPK RF", article="113", title="Notice"),
        ],
        supporting_sources=[SourceRef(law="ECHR", article="6", title="Fair trial")],
        retrieved_articles=[
            {"law": "GPK RF", "article": "9", "excerpt": "Proceedings in Russian..."},
        ],
        matched_issues=["interpreter_issue", "notice_issue"],
        retrieval_notes=["test"],
    )


def _minimal_output(*, laws: list[tuple[str, str]]) -> LegalStrategyAgent2Output:
    primary = [
        PrimaryBasisItem(
            provision=SourceRef(law=a, article=b),
            why_it_matters="Because facts align.",
            connected_facts=["Foreign citizen"],
        )
        for a, b in laws
    ]
    return LegalStrategyAgent2Output(
        case_theory="Core problem: access to language and notice.",
        primary_legal_basis=primary,
        supporting_legal_basis=[],
        fact_to_law_mapping=[],
        strategic_assessment=StrategicAssessmentBlock(),
        missing_evidence_gaps=MissingEvidenceBlock(),
        recommended_next_steps=[],
        draft_argument_direction="The case should argue that procedural safeguards were not observed.",
        insufficient_support_items=[],
    )


class _ThrowingProvider(BaseLLMProvider):
    def invoke_structured(self, system_prompt, user_prompt, schema):
        raise RuntimeError("network down")

    def invoke_text(self, system_prompt, user_prompt):
        return ""


def test_happy_path_valid_structured_output():
    inp = LegalStrategyAgent2Input(
        case_id="C-1",
        jurisdiction="Russia",
        cleaned_summary="No interpreter; no notice.",
        facts=["Foreign citizen", "No interpreter"],
        issue_flags=["interpreter_issue"],
        claims_or_questions=["Strategy?"],
        legal_evidence_pack=_gpk_pack(),
    )
    mock = MagicMock(spec=BaseLLMProvider)
    mock.invoke_structured.return_value = _minimal_output(
        laws=[("GPK RF", "9"), ("GPK RF", "113")],
    )
    svc = LegalStrategyAgent2Service(mock, model_name="mock")
    result = svc.run(inp)
    assert result.output.case_theory
    assert result.audit.contract_ok is True
    assert result.audit.repair_count == 0
    mock.invoke_structured.assert_called_once()
    user_msg = mock.invoke_structured.call_args[0][1]
    system_msg = mock.invoke_structured.call_args[0][0]
    assert USER_MESSAGE_HEADER in user_msg
    assert "Foreign citizen" in user_msg
    # Case facts must not be smuggled into the fixed system instruction channel.
    assert "Foreign citizen" not in system_msg


def test_contract_raises_when_citing_unknown_provision():
    inp = LegalStrategyAgent2Input(
        case_id="C-2",
        jurisdiction="Russia",
        cleaned_summary="x",
        facts=[],
        legal_evidence_pack=_gpk_pack(),
    )
    mock = MagicMock(spec=BaseLLMProvider)
    mock.invoke_structured.return_value = _minimal_output(laws=[("GPK RF", "999")])
    svc = LegalStrategyAgent2Service(mock, model_name="mock")
    with pytest.raises(Agent2OutputContractError) as ei:
        svc.run(inp, config=Agent2RunConfig(max_repair_attempts=0))
    assert ei.value.violations


def test_repair_second_pass_succeeds():
    inp = LegalStrategyAgent2Input(
        case_id="C-3",
        jurisdiction="Russia",
        cleaned_summary="x",
        facts=[],
        legal_evidence_pack=_gpk_pack(),
    )
    good = _minimal_output(laws=[("GPK RF", "9")])
    bad = _minimal_output(laws=[("GPK RF", "999")])
    mock = MagicMock(spec=BaseLLMProvider)
    mock.invoke_structured.side_effect = [bad, good]
    svc = LegalStrategyAgent2Service(mock, model_name="mock")
    result = svc.run(inp, config=Agent2RunConfig(max_repair_attempts=1))
    assert result.audit.repair_count == 1
    assert result.audit.contract_ok is True
    assert mock.invoke_structured.call_count == 2


def test_insufficient_evidence_partial_output_still_valid_schema():
    """Model returns empty primary list but valid schema — contract may pass if nothing cited."""
    inp = LegalStrategyAgent2Input(
        case_id="C-4",
        jurisdiction="EU",
        cleaned_summary="Thin facts",
        facts=["One fact"],
        legal_evidence_pack=_gpk_pack(),
    )
    out = LegalStrategyAgent2Output(
        case_theory="Insufficient material to assert strong claims.",
        primary_legal_basis=[],
        supporting_legal_basis=[],
        fact_to_law_mapping=[],
        strategic_assessment=StrategicAssessmentBlock(),
        missing_evidence_gaps=MissingEvidenceBlock(what_is_unclear=["timeline"]),
        recommended_next_steps=[],
        draft_argument_direction="The case should first clarify facts before legal theories.",
        insufficient_support_items=[
            InsufficientSupportItem(topic="causation", reason="Insufficient support in current evidence pack.")
        ],
    )
    mock = MagicMock(spec=BaseLLMProvider)
    mock.invoke_structured.return_value = out
    svc = LegalStrategyAgent2Service(mock, model_name="mock")
    result = svc.run(inp, config=Agent2RunConfig(strict_reliability=True))
    assert result.output.insufficient_support_items
    assert result.audit.contract_ok is True


def test_combined_issue_flags_mapping():
    inp = LegalStrategyAgent2Input(
        case_id="C-5",
        jurisdiction="Russia",
        cleaned_summary="Interpreter and notice",
        facts=["A", "B"],
        issue_flags=["interpreter_issue", "language_issue", "notice_issue"],
        legal_evidence_pack=_gpk_pack(),
    )
    mock = MagicMock(spec=BaseLLMProvider)
    mock.invoke_structured.return_value = _minimal_output(
        laws=[("GPK RF", "9"), ("GPK RF", "113"), ("ECHR", "6")],
    )
    svc = LegalStrategyAgent2Service(mock, model_name="mock")
    result = svc.run(inp)
    assert len(result.output.primary_legal_basis) == 3


def test_invocation_failure_emits_audit_and_raises():
    inp = LegalStrategyAgent2Input(
        case_id="C-6",
        jurisdiction="X",
        cleaned_summary="",
        legal_evidence_pack=_gpk_pack(),
    )
    svc = LegalStrategyAgent2Service(_ThrowingProvider(), model_name="x")
    with pytest.raises(Agent2InvocationError):
        svc.run(inp)
