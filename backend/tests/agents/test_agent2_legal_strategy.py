"""Tests for Agent 2 legal strategy service (mocked LLM)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.modules.common.agents.agent2_legal_strategy.errors import Agent2InvocationError
from app.modules.common.agents.agent2_legal_strategy.input_schemas import (
    CaseDocumentInput,
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

# Passes Agent 2 legal-depth validation (min length + markers + no forbidden phrases).
LITIGATION_STUB_WHY = (
    "The party's factual narrative, read against the retrieved excerpt, demonstrates non-compliance with the "
    "procedural obligations imposed by the cited provision; this constitutes a procedural defect and a violation "
    "of fair-trial guarantees in substance. The breach therefore results in identifiable grounds for reversal "
    "or remand where prejudice is shown. Invalid notice or invalid absentee proceedings may follow if service "
    "and participation were not lawfully secured; the court must assess whether the defect undermines the judgment."
)


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


def _full_case_pack() -> LegalEvidencePack:
    return LegalEvidencePack(
        primary_sources=[
            SourceRef(law="ГПК РФ", article="9"),
            SourceRef(law="ГПК РФ", article="112"),
            SourceRef(law="ГПК РФ", article="113"),
            SourceRef(law="ГПК РФ", article="116"),
            SourceRef(law="ГПК РФ", article="162"),
            SourceRef(law="ГПК РФ", article="167"),
            SourceRef(law="ГПК РФ", article="407"),
            SourceRef(law="СК РФ", article="80"),
            SourceRef(law="СК РФ", article="81"),
        ],
        supporting_sources=[SourceRef(law="ГПК РФ", article="398"), SourceRef(law="ЕКПЧ", article="6")],
        retrieved_articles=[
            {"law": "ГПК РФ", "article": "9", "excerpt": "x"},
            {"law": "ГПК РФ", "article": "112", "excerpt": "x"},
            {"law": "ГПК РФ", "article": "113", "excerpt": "x"},
            {"law": "ГПК РФ", "article": "116", "excerpt": "x"},
            {"law": "ГПК РФ", "article": "162", "excerpt": "x"},
            {"law": "ГПК РФ", "article": "167", "excerpt": "x"},
            {"law": "ГПК РФ", "article": "407", "excerpt": "x"},
            {"law": "СК РФ", "article": "80", "excerpt": "x"},
            {"law": "СК РФ", "article": "81", "excerpt": "x"},
        ],
        matched_issues=[
            "interpreter_issue",
            "notice_issue",
            "service_address_issue",
            "foreign_service_issue",
            "missed_deadline_due_to_service_issue",
            "alimony_issue",
        ],
        retrieval_notes=["test"],
    )


def _minimal_output(*, laws: list[tuple[str, str]]) -> LegalStrategyAgent2Output:
    primary = [
        PrimaryBasisItem(
            provision=SourceRef(law=a, article=b),
            why_it_matters=LITIGATION_STUB_WHY,
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


def test_contract_violation_falls_back_to_deterministic_pack():
    """Unknown article cites cannot be repaired; after depth attempts the service uses deterministic fallback."""
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
    result = svc.run(inp, config=Agent2RunConfig(max_repair_attempts=0))
    arts = {p.provision.article for p in result.output.primary_legal_basis}
    assert "999" not in arts
    assert result.audit.contract_ok is True


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


def test_invocation_failure_after_retries_uses_deterministic_fallback():
    """Three failed LLM invocations trigger deterministic litigation fallback (no client-visible crash)."""
    inp = LegalStrategyAgent2Input(
        case_id="C-6",
        jurisdiction="X",
        cleaned_summary="",
        legal_evidence_pack=_gpk_pack(),
    )
    svc = LegalStrategyAgent2Service(_ThrowingProvider(), model_name="x")
    result = svc.run(inp)
    assert result.output.case_theory
    assert result.output.primary_legal_basis
    assert result.audit.contract_ok is True


def test_undercoverage_with_insufficient_items_forced_to_grounded_fallback():
    inp = LegalStrategyAgent2Input(
        case_id="C-7",
        jurisdiction="Russia",
        cleaned_summary="Cross-border alimony procedural defects",
        facts=["foreign address", "no interpreter", "late awareness of judgment"],
        issue_flags=[
            "interpreter_issue",
            "notice_issue",
            "service_address_issue",
            "foreign_service_issue",
            "missed_deadline_due_to_service_issue",
            "alimony_issue",
        ],
        legal_evidence_pack=_full_case_pack(),
    )
    undercovered = LegalStrategyAgent2Output(
        case_theory="Thin summary",
        primary_legal_basis=[],
        supporting_legal_basis=[],
        fact_to_law_mapping=[],
        strategic_assessment=StrategicAssessmentBlock(),
        missing_evidence_gaps=MissingEvidenceBlock(),
        recommended_next_steps=[],
        draft_argument_direction="",
        insufficient_support_items=[
            InsufficientSupportItem(topic="deadline restoration"),
            InsufficientSupportItem(topic="foreign service"),
            InsufficientSupportItem(topic="interpreter"),
        ],
    )
    mock = MagicMock(spec=BaseLLMProvider)
    mock.invoke_structured.return_value = undercovered
    svc = LegalStrategyAgent2Service(mock, model_name="mock")
    result = svc.run(inp)
    out = result.output
    assert out.case_theory
    assert out.primary_legal_basis
    assert out.recommended_next_steps
    assert out.insufficient_support_items == []


def test_extraction_mode_uses_deterministic_ids_with_case_documents():
    inp = LegalStrategyAgent2Input(
        case_id="C-EXTRACT-1",
        jurisdiction="Russia",
        cleaned_summary="Procedural defects in notice and service.",
        facts=["No proper notice to foreign address"],
        issue_flags=["notice_issue", "foreign_service_issue"],
        legal_evidence_pack=_full_case_pack(),
        case_documents=[
            CaseDocumentInput(
                primary_document_id="judgment-2026-04-01",
                document_type="judgment",
                document_date="2026-04-01",
                document_role="court",
                title="First instance judgment",
                content="Full judgment text with legal reasoning.",
                source_pages=["p.1-12"],
                full_text_reference="blob://judgment-2026-04-01",
            )
        ],
    )
    # Force fallback so we test deterministic extraction builder.
    svc = LegalStrategyAgent2Service(_ThrowingProvider(), model_name="x")
    result = svc.run_extraction(inp)
    out = result.output

    assert out.schema_version == "agent2_legal_extraction.v1"
    assert out.case_id == "C-EXTRACT-1"
    assert out.groups
    assert out.groups[0].group_id == "case::C-EXTRACT-1::group::judgments"
    assert out.groups[0].documents[0].doc_id.startswith("case::C-EXTRACT-1::doc::")
    assert out.issues[0].issue_id.startswith("case::C-EXTRACT-1::issue::")
    assert out.defense_blocks[0].defense_id.startswith("case::C-EXTRACT-1::defense::")
