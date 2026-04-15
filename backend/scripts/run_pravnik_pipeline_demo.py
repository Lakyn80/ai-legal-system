"""
In-process demo: Agent 1 (fixed pack) → Agent 2 (LLM or canned) → agent_pravnik.

Usage (from repo root or backend):
  python scripts/run_pravnik_pipeline_demo.py
  python scripts/run_pravnik_pipeline_demo.py --output-json out.json

Prints one JSON object (Agent 2 + agent_pravnik structured output, flags) then the final document section.
With --output-json, the same JSON is written to a file (add the printed document manually from the console
if you need it inside the file).

Requires OPENAI API key in .env for live LLM; otherwise uses canned Agent 2 + deterministic pravnik-quality fallback.
LLM output token cap defaults to 5000 (env LLM_MAX_OUTPUT_TOKENS or LLM_DEPTH).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as script from backend/
if __name__ == "__main__":
    _root = Path(__file__).resolve().parents[1]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from app.core.config import get_settings
from app.modules.common.agents.agent2_legal_strategy.input_schemas import LegalEvidencePack, LegalStrategyAgent2Input
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
from app.modules.common.agents.agent2_legal_strategy.service import LegalStrategyAgent2Service
from app.modules.common.llm.provider import build_llm_provider
from app.modules.russia.agents.agent_pravnik.schemas import AgentPravnikRuInput
from app.modules.russia.agents.agent_pravnik.service import LegalPravnikAgentService, PravnikRunConfig


def _evidence_pack_agent1() -> LegalEvidencePack:
    """Simulated Agent 1 retrieval — fixed articles relevant to notice / interpreter / alimony / deadlines."""
    return LegalEvidencePack(
        primary_sources=[
            SourceRef(law="ГПК РФ", article="9"),
            SourceRef(law="ГПК РФ", article="112"),
            SourceRef(law="ГПК РФ", article="113"),
            SourceRef(law="ГПК РФ", article="116"),
            SourceRef(law="ГПК РФ", article="162"),
            SourceRef(law="ГПК РФ", article="167"),
            SourceRef(law="ГПК РФ", article="330"),
            SourceRef(law="ГПК РФ", article="407"),
            SourceRef(law="СК РФ", article="80"),
            SourceRef(law="СК РФ", article="81"),
        ],
        supporting_sources=[SourceRef(law="ГПК РФ", article="398"), SourceRef(law="ЕКПЧ", article="6")],
        retrieved_articles=[
            {"law": "ГПК РФ", "article": "9", "excerpt": "…"},
            {"law": "ГПК РФ", "article": "113", "excerpt": "…"},
            {"law": "СК РФ", "article": "80", "excerpt": "…"},
        ],
        matched_issues=[
            "notice_issue",
            "interpreter_issue",
            "foreign_service_issue",
            "alimony_issue",
            "missed_deadline_due_to_service_issue",
        ],
        retrieval_notes=["simulated_agent1_taxonomy"],
    )


_RU_WHY = (
    "По фактам дела установлено несоблюдение требований к извещению и участию стороны: извещение не было "
    "надлежащим образом вручено по адресу за пределами РФ, вследствие чего сторона не была уведомлена о заседании. "
    "Ссылка на статью ГПК РФ из выдержки показывает обязанность суда обеспечить надлежащее извещение; это нарушение "
    "является существенным процессуальным дефектом и лишает сторону права на защиту в полном объёме. "
    "Следствием является риск незаконности судебного акта и наличие оснований для отмены или изменения решения "
    "в апелляции; суд должен оценить влияние дефекта на исход спора и на установление фактов по алиментам."
)


def _canned_agent2(pack: LegalEvidencePack) -> LegalStrategyAgent2Output:
    """Rich Russian analysis — used when LLM unavailable; grounded in pack articles only."""
    primary = [
        PrimaryBasisItem(
            provision=SourceRef(law="ГПК РФ", article="113"),
            why_it_matters=_RU_WHY,
            connected_facts=[
                "Гражданин Чехии; извещение не поступало на чешский адрес",
                "Сведения о решении получены при исполнительном производстве",
            ],
        ),
        PrimaryBasisItem(
            provision=SourceRef(law="ГПК РФ", article="9"),
            why_it_matters=_RU_WHY,
            connected_facts=["Отсутствие переводчика при языковом барьере"],
        ),
        PrimaryBasisItem(
            provision=SourceRef(law="СК РФ", article="80"),
            why_it_matters=_RU_WHY + " Материальное право об алиментах применимо лишь при законном процессе.",
            connected_facts=["Спор об алиментах на детей"],
        ),
    ]
    return LegalStrategyAgent2Output(
        case_theory=(
            "Теория дела: процессуальная законность первой инстанции подорвана дефектами извещения и участия; "
            "материальные выводы об алиментах не могут считаться достаточно проверенными при лишении стороны "
            "возможности надлежащего участия и перевода."
        ),
        primary_legal_basis=primary,
        supporting_legal_basis=[
            SupportingBasisItem(
                provision=SourceRef(law="ГПК РФ", article="112"),
                how_it_reinforces="Правило о восстановлении срока усиливает линию о доступе к обжалованию при позднем "
                "сведении о решении при обстоятельствах, не зависящих от стороны.",
            ),
        ],
        fact_to_law_mapping=[
            FactToLawRow(
                issue_name="Извещение и участие",
                relevant_facts=["Нет надлежащего уведомления по чешскому адресу", "Нет переводчика"],
                legal_provisions=[SourceRef(law="ГПК РФ", article="113"), SourceRef(law="ГПК РФ", article="9")],
                assessment_strength="strong",
                comment=_RU_WHY,
            ),
        ],
        strategic_assessment=StrategicAssessmentBlock(
            strongest_arguments=["Существенные нарушения процедуры извещения и языка."],
            weaker_arguments=["Доказательства фактического получения копий решения могут быть спорными."],
            likely_vulnerabilities=["Необходимость подтвердить адрес для корреспонденции."],
            opposing_side_may_argue=["Формальная отсылка к заявленному адресу в РФ."],
        ),
        missing_evidence_gaps=MissingEvidenceBlock(
            what_is_unclear=["Полный текст судебного акта и даты направления копий"],
            needed_documents_or_facts=["Почтовые реквизиты отправления на адрес в Чехии"],
        ),
        recommended_next_steps=[
            NextStepItem(
                step_order=1,
                action="Подать апелляционную жалобу с ходатайством о восстановлении срока при необходимости.",
            ),
        ],
        draft_argument_direction=(
            "Главная линия: отмена решения за существенные нарушения ГПК РФ и СК РФ с направлением на новое "
            "рассмотрение; альтернативно — изменение акта при установлении иных нарушений."
        ),
        insufficient_support_items=[],
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args()

    settings = get_settings()
    llm = build_llm_provider(settings)
    live = settings.llm_provider.lower() == "openai" and bool(settings.llm_api_key)

    pack = _evidence_pack_agent1()
    summary_ru = (
        "Гражданин Чешской Республики. Спор об алиментах. Суд в России рассмотрел дело без надлежащего извещения "
        "по адресу в Чехии, без участия стороны и без переводчика; о решении стало известно при возбуждении "
        "исполнительного производства."
    )
    facts_ru = [
        "Заявитель — гражданин ЧР, место жительства — Чешская Республика.",
        "Судебные извещения/повестки на чешский адрес надлежащим образом не доставлялись либо не обеспечивали реальное "
        "сведение о заседании.",
        "В судебном заседании отсутствовал переводчик при наличии языкового барьера.",
        "Сторона не присутствовала при рассмотрении; возражений по существу не заявляла.",
        "О существовании решения и его содержании сторона узнала при исполнительном производстве (взыскание алиментов).",
    ]

    a2_inp = LegalStrategyAgent2Input(
        case_id="demo-cz-ru-alimony-pravnik",
        jurisdiction="Russia",
        cleaned_summary=summary_ru,
        facts=facts_ru,
        timeline=[],
        issue_flags=pack.matched_issues,
        claims_or_questions=["Обжалование решения; восстановление срока; отмена."],
        legal_evidence_pack=pack,
    )

    if live:
        a2_result = LegalStrategyAgent2Service(llm, model_name=settings.llm_model).run(a2_inp)
        agent2_out = a2_result.output
    else:
        agent2_out = _canned_agent2(pack)

    pravnik_inp = AgentPravnikRuInput(
        case_id=a2_inp.case_id,
        jurisdiction="Russia",
        document_kind="appeal_draft",
        work_mode="strict_litigation",
        legal_evidence_pack=pack,
        agent2_output=agent2_out,
        cleaned_summary=summary_ru,
        facts=facts_ru,
        issue_flags=list(pack.matched_issues),
        timeline=[],
        claims_or_questions=a2_inp.claims_or_questions,
        procedural_posture="Апелляционное обжалование решения суда первой инстанции (проект).",
    )

    if live:
        pr_result = LegalPravnikAgentService(
            llm,
            cfg=PravnikRunConfig(model_name=settings.llm_model),
        ).run(pravnik_inp)
        pravnik_out = pr_result.output
        used_fb = pr_result.used_deterministic_fallback
    else:
        from app.modules.russia.agents.agent_pravnik.fallback_ru import build_deterministic_fallback

        pravnik_out = build_deterministic_fallback(pravnik_inp)
        used_fb = True

    out_obj = {
        "agent1_simulated": "fixed LegalEvidencePack (taxonomy issues + articles)",
        "llm_max_output_tokens": settings.llm_max_output_tokens,
        "agent2_live_llm": live,
        "agent2_output": json.loads(agent2_out.model_dump_json()),
        "agent_pravnik_live_llm": live,
        "used_deterministic_fallback": used_fb,
        "agent_pravnik_output": json.loads(pravnik_out.model_dump_json()),
    }
    text = json.dumps(out_obj, ensure_ascii=False, indent=2)
    print(text)
    print("\n=== FINAL LEGAL DOCUMENT ===\n")
    doc = pravnik_out.full_document_markdown or ""
    if not doc.strip():
        parts = [
            pravnik_out.document_title,
            "",
            pravnik_out.header_block,
            "",
            "ОБСТОЯТЕЛЬСТВА",
            pravnik_out.facts_section,
            "",
            "ПРАВОВАЯ ПОЗИЦИЯ",
            pravnik_out.legal_argument_section,
            "",
            "НАРУШЕНИЯ И ПОСЛЕДСТВИЯ",
            pravnik_out.violation_and_consequence,
            "",
            "ПРОСИТЕЛЬНАЯ ЧАСТЬ",
            "\n".join(pravnik_out.requested_relief.primary_asks),
        ]
        doc = "\n".join(parts)
    print(doc)

    if args.output_json:
        args.output_json.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
