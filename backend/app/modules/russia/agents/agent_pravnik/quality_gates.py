"""
Quality gates for agent_pravnik — aggressive litigation style, lengths, vocabulary (appeal_draft + strict_litigation).
"""
from __future__ import annotations

from app.modules.russia.agents.agent_pravnik.schemas import (
    AgentPravnikRuInput,
    AgentPravnikRuOutput,
    DocumentKindRuLiteral,
    PravnikWorkModeLiteral,
)

# MVP document + mode
MVP_DOCUMENT_KIND: DocumentKindRuLiteral = "appeal_draft"
MVP_WORK_MODE: PravnikWorkModeLiteral = "strict_litigation"

_MIN_LEGAL_ARGUMENT_CHARS = 1200
_MIN_FACTS_CHARS = 120
_MIN_VIOLATION_CHARS = 600
_MIN_PRIMARY_ASKS = 3

# English / generic AI — banned in narrative (case-insensitive)
_BANNED_EN_PHRASES: tuple[str, ...] = (
    "supports the issue",
    "is relevant",
    "may indicate",
    "provides context",
    "this paper",
)

# Russian banned fluff
_BANNED_RU_PHRASES: tuple[str, ...] = (
    "нейросеть",
    "в данной работе рассмотрим",
    "искусственный интеллект",
    "как модель",
    "в данной работе",
)

# Mandatory litigation vocabulary (substring checks on lowercased RU text)
_MANDATORY_SUBSTRINGS_RU: tuple[str, ...] = (
    "нарушен",  # нарушение / нарушены
    "существенн",  # существенное нарушение
    "лишен",  # лишение права на защиту (лишён / лишение)
    "незаконн",
    "надлежащим образом",
    "уведомл",  # уведомлён / уведомлен
    "подлежит отмене",
    "основанием для отмены",
    "лишил",  # лишило … участвовать — cover лишило/лишил
    "участвовать в процессе",
)

# Relief formulations — must appear in relief-related text (lowercase)
_RELIEF_REQUIRED: tuple[str, ...] = (
    "просим суд",
    "отменить решение",
    "направить дело на новое рассмотрение",
)

# Optional but requested: at least one of these (deadline restoration) if applicable — require one phrase
_RELIEF_OPTIONAL_PROCEDURAL = "восстановить срок"


def _combined_narrative(out: AgentPravnikRuOutput) -> str:
    return "\n".join(
        [
            out.facts_section,
            out.legal_argument_section,
            out.violation_and_consequence,
            out.header_block,
            out.procedural_background,
        ],
    )


def _relief_blob(out: AgentPravnikRuOutput) -> str:
    parts = list(out.requested_relief.primary_asks)
    parts.extend(out.requested_relief.alternative_asks)
    parts.extend(out.requested_relief.non_claim_procedural)
    return "\n".join(parts).lower()


def _empty_paragraphs(text: str) -> bool:
    """True if there is an empty block between double newlines."""
    for block in text.split("\n\n"):
        if block.strip() == "":
            return True
    return False


def _triple_newline(text: str) -> bool:
    return "\n\n\n" in text


def _paragraph_structure_violations(legal_text: str) -> list[str]:
    """
    Each substantial paragraph must read as an argument block: fact cue + norm cue + violation + consequence.
    Heuristic keyword buckets (RU).
    """
    paras = [p.strip() for p in legal_text.split("\n\n") if p.strip()]
    if len(paras) < 4:
        return [f"legal_argument_section: need at least 4 non-empty paragraphs, got {len(paras)}"]

    fact_cues = ("установлено", "имел место", "обстоятельств", "факт", "заявля", "сторон")
    norm_cues = ("ст.", "статья", "гпк", "ск рф", "норм", "кодекс")
    viol_cues = ("нарушен", "неправомерн", "существенн", "лишен", "не был")
    cons_cues = ("отмен", "направить", "восстанов", "последств", "основани", "подлежит")

    bad: list[str] = []
    for i, p in enumerate(paras):
        if len(p) < 120:
            continue
        pl = p.lower()
        has_fact = any(c in pl for c in fact_cues)
        has_norm = any(c in pl for c in norm_cues)
        has_viol = any(c in pl for c in viol_cues)
        has_cons = any(c in pl for c in cons_cues)
        if not (has_fact and has_norm and has_viol and has_cons):
            bad.append(
                f"paragraph[{i}]: missing argument skeleton (need fact+norm+violation+consequence cues): "
                f"fact={has_fact} norm={has_norm} viol={has_viol} cons={has_cons}",
            )
    return bad


def quality_gate_violations(inp: AgentPravnikRuInput, out: AgentPravnikRuOutput) -> list[str]:
    """
    Return human-readable reasons if output fails quality bar for configured document_kind/work_mode.
    """
    reasons: list[str] = []

    if out.document_kind != inp.document_kind:
        reasons.append(f"document_kind mismatch: output={out.document_kind!r} input={inp.document_kind!r}")
    if out.work_mode != inp.work_mode:
        reasons.append(f"work_mode mismatch: output={out.work_mode!r} input={inp.work_mode!r}")

    if inp.document_kind == MVP_DOCUMENT_KIND and inp.work_mode == MVP_WORK_MODE:
        if len(out.legal_argument_section or "") < _MIN_LEGAL_ARGUMENT_CHARS:
            reasons.append(
                f"legal_argument_section: too_short len={len(out.legal_argument_section)} "
                f"(min {_MIN_LEGAL_ARGUMENT_CHARS})",
            )
        if len(out.facts_section or "") < _MIN_FACTS_CHARS:
            reasons.append(
                f"facts_section: too_short len={len(out.facts_section)} (min {_MIN_FACTS_CHARS})",
            )
        if len(out.violation_and_consequence or "") < _MIN_VIOLATION_CHARS:
            reasons.append(
                f"violation_and_consequence: too_short len={len(out.violation_and_consequence)} "
                f"(min {_MIN_VIOLATION_CHARS})",
            )
        if len(out.requested_relief.primary_asks) < _MIN_PRIMARY_ASKS:
            reasons.append(
                f"requested_relief.primary_asks: need at least {_MIN_PRIMARY_ASKS} concrete points, "
                f"got {len(out.requested_relief.primary_asks)}",
            )

        narr = _combined_narrative(out).lower()
        for sub in _MANDATORY_SUBSTRINGS_RU:
            if sub.lower() not in narr:
                reasons.append(f"mandatory_vocabulary_missing: {sub!r}")

        rb = _relief_blob(out)
        for sub in _RELIEF_REQUIRED:
            if sub not in rb:
                reasons.append(f"relief_formulation_missing: {sub!r}")
        if _RELIEF_OPTIONAL_PROCEDURAL not in rb:
            reasons.append(f"relief_formulation_missing: {_RELIEF_OPTIONAL_PROCEDURAL!r}")

        blob = narr
        for ph in _BANNED_RU_PHRASES:
            if ph.lower() in blob:
                reasons.append(f"banned_phrase_ru={ph!r}")
        blob_en = _combined_narrative(out).lower()
        for ph in _BANNED_EN_PHRASES:
            if ph.lower() in blob_en:
                reasons.append(f"banned_phrase_en={ph!r}")

        for label, text in (
            ("legal_argument_section", out.legal_argument_section),
            ("violation_and_consequence", out.violation_and_consequence),
        ):
            if _empty_paragraphs(text or ""):
                reasons.append(f"{label}: empty paragraph block")
            if _triple_newline(text or ""):
                reasons.append(f"{label}: triple_newline (no empty filler blocks)")

        reasons.extend(_paragraph_structure_violations(out.legal_argument_section or ""))

    return reasons


def cyrillic_ratio(text: str) -> float:
    """Share of Cyrillic letters in alphabetic chars — language regression heuristic."""
    if not text:
        return 0.0
    cyr = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    latin = sum(1 for c in text if "a" <= c.lower() <= "z")
    denom = cyr + latin
    return cyr / denom if denom else 0.0
