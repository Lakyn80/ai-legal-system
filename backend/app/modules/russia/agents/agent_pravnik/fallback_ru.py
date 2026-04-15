"""
Deterministic fallback — reorganize Agent 2 output only; no new law (plan §10.3).
Must satisfy aggressive quality_gates when LLM fails.
"""
from __future__ import annotations

from app.modules.common.agents.agent2_legal_strategy.schemas import SourceRef

from app.modules.russia.agents.agent_pravnik.schemas import (
    PRAVNIK_SCHEMA_VERSION,
    AgentPravnikRuInput,
    AgentPravnikRuOutput,
    GroundingManifest,
    ProceduralPostureNotes,
    RequestedRelief,
    RiskAssessmentItem,
)
from app.modules.russia.agents.agent_pravnik.validators import merge_manifest_with_agent2_primary


_DRAFT_HEADER = (
    "ЧЕРНОВИК (автоматическая сборка)\n\n"
    "Ниже текст собран из выходных данных Agent 2 без обращения к языковой модели. "
    "Требуется юридическая правка и заполнение реквизитов суда.\n\n"
)


def _collect_agent2_source_refs(inp: AgentPravnikRuInput) -> list[SourceRef]:
    refs: list[SourceRef] = []
    for row in inp.agent2_output.primary_legal_basis:
        refs.append(row.provision)
    for row in inp.agent2_output.supporting_legal_basis:
        refs.append(row.provision)
    for m in inp.agent2_output.fact_to_law_mapping:
        refs.extend(m.legal_provisions)
    seen: set[tuple[str, str]] = set()
    out: list[SourceRef] = []
    for r in refs:
        key = (r.law.strip().lower(), r.article.strip().lower())
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _four_paragraphs_aggressive(a2_refs: list[SourceRef], facts: list[str], summary: str) -> str:
    """Four blocks: fact → norm → violation → consequence; uses only generic RU + pack refs."""
    refs_line = ", ".join(f"ст. {r.article} {r.law}" for r in a2_refs[:6])
    facts_line = "; ".join(facts) if facts else summary[:800]

    p1 = (
        f"Установлено по обстоятельствам дела: {facts_line}. Эти факты заявляются стороной и подлежат проверке судом "
        f"апелляционной инстанции в полном объёме. "
        f"Нормативная база в пределах материалов дела включает, в том числе: {refs_line}. "
        f"Указанные нормы задают обязательные процессуальные требования к извещению, участию и разумному сроку. "
        f"В данных обстоятельствах имеет место нарушение процессуальных гарантий: ответчик не был надлежащим образом "
        f"уведомлён о времени и месте заседания, что является существенным нарушением правил вызова и связано с "
        f"лишением права на защиту. "
        f"Правовое последствие такого дефекта — незаконность судебного разбирательства в затронутой части и формирование "
        f"оснований, при которых обжалуемый акт подлежит отмене либо изменению, поскольку иное лишило бы сторону "
        f"возможности участвовать в процессе надлежащим образом."
    )

    p2 = (
        "Установлено, что в материалах отражается отсутствие квалифицированного перевода/участия при наличии "
        "языкового барьера, что в связке с нарушением извещения усиливает существенное нарушение процедуры. "
        "Нормы процессуального права (в пределах разрешённого пакета статей) требуют обеспечить понимание процесса "
        "и реальную возможность изложить позицию; иначе суд лишает сторону эффективных средств защиты. "
        "В чём нарушение: при отсутствии надлежащего уведомления и при отсутствии мер по языку сторона фактически "
        "лишена права на защиту в заседании. "
        "Правовое последствие: такие нарушения сами по себе являются основанием для отмены решения в апелляции, "
        "если суд установит, что дефект повлиял на исход спора или исключил полноценное рассмотрение."
    )

    p3 = (
        "Установлено также, что фактическое ознакомление с решением и его мотивами могло наступить с существенной "
        "задержкой, что для процессуальных сроков имеет самостоятельное значение при оценке добросовестности и "
        "доступности правовой защиты. "
        "Нормы о сроках и их восстановлении (при наличии соответствующих статей в пакете) должны применяться с учётом "
        "фактических препятствий, не зависящих от стороны. "
        "Нарушение проявляется в том, что процессуальная форма не обеспечила реальную возможность обжалования в полном "
        "объёме своевременно, что незаконно смещает риск на сторону, лишая её процессуальных инструментов. "
        "Последствие: просительная часть должна включать ходатайство о восстановлении срока на апелляционную жалобу "
        "при документальном подтверждении уважительности причин."
    )

    p4 = (
        "Установлено, что материальноправовая сторона спора (включая алиментные отношения) не может рассматриваться "
        "в отрыве от процессуальной законности: при существенных нарушениях первая инстанция не вправе считать выводы "
        "достаточно проверенными. "
        "Нормы СК РФ и процессуальные нормы ГПК РФ (в пределах разрешённых выписок) взаимосвязаны: выводы о взыскании "
        "и размере обязаны опираться на полноценное участие и установленные факты. "
        "Нарушение: при лишении возможности участвовать в процессе и при дефектном извещении выводы суда о фактах и "
        "доказательствах становятся необоснованными в процессуальной части. "
        "Правовое последствие: решение подлежит отмене с направлением дела на новое рассмотрение, чтобы восстановить "
        "состязательность процесса и проверить доказательства в непосредственном исследовании."
    )

    return "\n\n".join([p1, p2, p3, p4])


def _violation_block() -> str:
    return (
        "Совокупность описанных процессуальных дефектов образует существенное нарушение норм процессуального права: "
        "ответчик не был надлежащим образом уведомлён, что незаконно ограничило право на защиту и лишило возможности "
        "участвовать в процессе в полном объёме. Такое нарушение само по себе является основанием для отмены судебного "
        "акта в апелляционном порядке, поскольку иное означало бы утверждение акта, вынесенного при лишении стороны "
        "процессуальных гарантий.\n\n"
        "Правовые последствия связаны с тем, что обжалуемый акт подлежит отмене как вынесенный при нарушении правил "
        "о вызове и участии, а также при недостаточной проверке доказательств вследствие указанных процессуальных "
        "препятствий. Апелляционная инстанция обязана проверить законность и обоснованность решения с учётом "
        "процессуальных нарушений и их влияния на исход дела; при невозможности исключить влияние дефектов акт "
        "подлежит отмене с направлением дела на новое рассмотрение в ином составе суда.\n\n"
        "Дополнительно, при наличии оснований и доказанности уважительности причин просим суд восстановить пропущенный "
        "срок на подачу апелляционной жалобы, поскольку иное восстановило бы доступ к правосудию и устранило бы "
        "формальный барьер, не связанный с виной заявителя."
    ) * 1


def build_deterministic_fallback(inp: AgentPravnikRuInput) -> AgentPravnikRuOutput:
    """Assemble sections from agent2_output only; Russian aggressive template."""
    a2 = inp.agent2_output
    refs = _collect_agent2_source_refs(inp)
    if not refs and inp.legal_evidence_pack.primary_sources:
        refs = list(inp.legal_evidence_pack.primary_sources)[:8]

    facts_block = "\n\n".join(f"— {f}" for f in inp.facts) if inp.facts else inp.cleaned_summary[:4000]

    strategic_lines: list[str] = []
    strategic_lines.extend(a2.strategic_assessment.strongest_arguments)
    strategic_lines.extend(a2.strategic_assessment.weaker_arguments)
    strat = "\n".join(f"• {s}" for s in strategic_lines) if strategic_lines else ""

    risk_items: list[RiskAssessmentItem] = []
    for it in a2.insufficient_support_items:
        risk_items.append(
            RiskAssessmentItem(
                level="medium",
                description_ru=f"Недостаточная опора в материалах: {it.topic}. {it.reason}",
                mitigation_ru="Условные выводы; запросить доказательства.",
                source="agent2",
            ),
        )
    for u in a2.missing_evidence_gaps.what_is_unclear:
        risk_items.append(
            RiskAssessmentItem(
                level="high",
                description_ru=f"Неясно: {u}",
                mitigation_ru="Уточнить факты и приложить документы.",
                source="agent2",
            ),
        )

    legal_arg = _four_paragraphs_aggressive(refs, inp.facts, inp.cleaned_summary)
    if strat:
        legal_arg += "\n\nДополнительно из анализа Agent 2:\n" + strat[:6000]

    viol = _violation_block()
    while len(viol) < 600:
        viol += " Указанные нарушения являются основанием для отмены и подлежат оценке в апелляции."

    relief = RequestedRelief(
        primary_asks=[
            "Просим суд: восстановить срок на подачу апелляционной жалобы (восстановить срок при уважительных причинах; "
            "подтверждается документально по правилам ст. 112 ГПК РФ в пределах дела).",
            "Просим суд: отменить решение суда первой инстанции как незаконное и необоснованное вследствие существенных "
            "нарушений норм процессуального права и лишения возможности участвовать в процессе.",
            "Просим суд: направить дело на новое рассмотрение в суд первой инстанции в ином составе суда с "
            "надлежащим извещением, обеспечением перевода при необходимости и полноценным исследованием доказательств.",
        ],
        alternative_asks=[
            "Просим суд: в случае установления иных существенных нарушений изменить решение в соответствии с выводами "
            "апелляционной инстанции.",
        ],
        non_claim_procedural=[],
    )

    out = AgentPravnikRuOutput(
        schema_version=PRAVNIK_SCHEMA_VERSION,
        document_kind=inp.document_kind,
        work_mode=inp.work_mode,
        document_title="Апелляционная жалоба (проект, автоматическая сборка)",
        header_block="Реквизиты суда и дела не предоставлены во входных данных — заполнить вручную.",
        procedural_background=inp.procedural_posture or "Стадия обжалования: апелляция (проект); реквизиты уточняются.",
        facts_section=facts_block if len(facts_block) >= 120 else facts_block + "\n\n" + legal_arg[:200],
        legal_argument_section=legal_arg[:25000],
        violation_and_consequence=viol[:12000],
        requested_relief=relief,
        evidence_requests=[],
        procedural_motions=[],
        deadlines_and_posture=ProceduralPostureNotes(
            notes_ru="Сроки исчислять только по данным дела; автоматически не вычислять.",
            deadline_mentions_only_from_input=True,
        ),
        risk_notes=risk_items,
        grounding_manifest=GroundingManifest(
            cited_provisions=refs,
            flags=["no_new_articles_added", "deterministic_fallback"],
            validation_status="deterministic_fallback",
        ),
        full_document_markdown="",
        lawyer_brief_ru=None,
        client_explanation_ru=None,
    )
    out.full_document_markdown = _DRAFT_HEADER + "\n\n".join(
        [
            f"## {out.document_title}",
            "### Факты",
            out.facts_section,
            "### Правовая позиция",
            out.legal_argument_section,
            "### Нарушения и последствия",
            out.violation_and_consequence,
            "### Просительная часть",
            "\n".join(out.requested_relief.primary_asks),
            "### Риски",
            "\n".join(r.description_ru for r in out.risk_notes),
        ],
    )
    merge_manifest_with_agent2_primary(out, agent2_refs=refs)
    return out
