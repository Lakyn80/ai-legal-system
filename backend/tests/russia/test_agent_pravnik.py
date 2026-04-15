"""Tests for agent_pravnik — contract, grounding, MVP appeal_draft + strict_litigation."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.modules.common.agents.agent2_legal_strategy.input_schemas import LegalEvidencePack
from app.modules.common.agents.agent2_legal_strategy.schemas import (
    LegalStrategyAgent2Output,
    MissingEvidenceBlock,
    PrimaryBasisItem,
    SourceRef,
    StrategicAssessmentBlock,
)
from app.modules.common.llm.provider import BaseLLMProvider

from app.modules.russia.agents.agent_pravnik.errors import PravnikInputError
from app.modules.russia.agents.agent_pravnik.schemas import AgentPravnikRuInput, AgentPravnikRuOutput
from app.modules.russia.agents.agent_pravnik.fallback_ru import build_deterministic_fallback
from app.modules.russia.agents.agent_pravnik.service import LegalPravnikAgentService, PravnikRunConfig
from app.modules.russia.agents.agent_pravnik.validators import pravnik_contract_violations


def _gpk_pack() -> LegalEvidencePack:
    return LegalEvidencePack(
        primary_sources=[
            SourceRef(law="GPK RF", article="9"),
            SourceRef(law="GPK RF", article="113"),
        ],
        supporting_sources=[],
        retrieved_articles=[
            {"law": "GPK RF", "article": "9", "excerpt": "…"},
            {"law": "GPK RF", "article": "113", "excerpt": "…"},
        ],
        matched_issues=["notice_issue"],
        retrieval_notes=["test"],
    )


def _minimal_agent2() -> LegalStrategyAgent2Output:
    return LegalStrategyAgent2Output(
        case_theory="Теория дела: нарушены гарантии надлежащего извещения и участия.",
        primary_legal_basis=[
            PrimaryBasisItem(
                provision=SourceRef(law="GPK RF", article="113"),
                why_it_matters="Статья 113 ГПК РФ устанавливает требования к вручению судебных извещений; "
                "их несоблюдение влечёт процессуальные последствия.",
                connected_facts=["Отсутствие надлежащего извещения"],
            ),
        ],
        supporting_legal_basis=[],
        fact_to_law_mapping=[],
        strategic_assessment=StrategicAssessmentBlock(
            strongest_arguments=["Нарушение сроков и порядка извещения."],
        ),
        missing_evidence_gaps=MissingEvidenceBlock(),
        recommended_next_steps=[],
        draft_argument_direction="Основной вектор: отмена решения за существенными нарушениями процедуры.",
        insufficient_support_items=[],
    )


def _valid_pravnik_output(inp: AgentPravnikRuInput) -> AgentPravnikRuOutput:
    """Same structure as deterministic fallback — satisfies aggressive quality_gates."""
    return build_deterministic_fallback(inp)


def _base_inp() -> AgentPravnikRuInput:
    return AgentPravnikRuInput(
        case_id="RU-PRAV-1",
        jurisdiction="Russia",
        document_kind="appeal_draft",
        work_mode="strict_litigation",
        legal_evidence_pack=_gpk_pack(),
        agent2_output=_minimal_agent2(),
        cleaned_summary="Краткое описание: иностранный гражданин, проблемы с извещением.",
        facts=["Сторона не получила повестку надлежащим образом.", "Заседание прошло без участия."],
        issue_flags=["notice_issue"],
        timeline=[],
        claims_or_questions=[],
    )


def test_happy_path_mock_llm():
    inp = _base_inp()
    mock = MagicMock(spec=BaseLLMProvider)
    mock.invoke_structured.return_value = _valid_pravnik_output(inp)
    svc = LegalPravnikAgentService(mock, cfg=PravnikRunConfig(model_name="mock"))
    result = svc.run(inp)
    assert result.output.document_kind == "appeal_draft"
    assert result.output.work_mode == "strict_litigation"
    assert result.audit.contract_ok is True
    assert result.used_deterministic_fallback is False
    assert pravnik_contract_violations(inp, result.output) == []
    mock.invoke_structured.assert_called()


def test_jurisdiction_guard():
    d = _base_inp().model_dump()
    d["jurisdiction"] = "Czech Republic"
    inp = AgentPravnikRuInput.model_construct(**d)
    mock = MagicMock(spec=BaseLLMProvider)
    svc = LegalPravnikAgentService(mock)
    with pytest.raises(PravnikInputError):
        svc.run(inp)


def test_grounding_violation_triggers_fallback():
    inp = _base_inp()
    bad = _valid_pravnik_output(inp)
    bad.grounding_manifest.cited_provisions = [SourceRef(law="GPK RF", article="9999")]
    mock = MagicMock(spec=BaseLLMProvider)
    mock.invoke_structured.return_value = bad
    svc = LegalPravnikAgentService(mock, cfg=PravnikRunConfig(model_name="mock"))
    result = svc.run(inp)
    assert result.used_deterministic_fallback is True
    assert pravnik_contract_violations(inp, result.output) == []


class _ThrowingProvider(BaseLLMProvider):
    def invoke_structured(self, system_prompt, user_prompt, schema):
        raise RuntimeError("network down")

    def invoke_text(self, system_prompt, user_prompt):
        return ""


def test_invoke_failure_uses_deterministic_fallback():
    inp = _base_inp()
    svc = LegalPravnikAgentService(_ThrowingProvider(), cfg=PravnikRunConfig(model_name="throw"))
    result = svc.run(inp)
    assert result.used_deterministic_fallback is True
    assert "ЧЕРНОВИК" in result.output.full_document_markdown
    assert pravnik_contract_violations(inp, result.output) == []


def test_contract_helper_detects_bad_article():
    inp = _base_inp()
    out = _valid_pravnik_output(inp)
    out.grounding_manifest.cited_provisions = [SourceRef(law="GPK RF", article="1")]
    v = pravnik_contract_violations(inp, out)
    assert len(v) >= 1
