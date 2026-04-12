"""
Deterministic state-machine parser for Russian law files (KonsultantPlus UTF-16 format).

Pipeline position: loader → **parser** → chunk_builder

Responsibilities:
- Consume raw_text from loader
- Skip the file header block (KonsultantPlus metadata, amendment list)
- Track Раздел / Глава context as articles are encountered
- Extract each Статья with its heading, article number, and body text
- Remove editor-only noise (Pass 1) before checking tombstone status (Pass 2)
- Split article body into logical parts (numbered частей or single chunk)
- Assign deterministic article_position from sequential counter

Does NOT:
- Perform any embeddings
- Write to Qdrant
- Use any LLM
- Import any common/retrieval modules
"""
from __future__ import annotations

import logging
import re
from enum import Enum, auto

from app.modules.russia.ingestion.schemas import (
    LawMetadata,
    ParseResult,
    RussianArticle,
    RussianArticlePart,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State machine states
# ---------------------------------------------------------------------------

class _State(Enum):
    HEADER     = auto()  # Before first structural marker — discard everything
    IN_SECTION = auto()  # After Раздел marker
    IN_CHAPTER = auto()  # After Глава marker
    IN_ARTICLE = auto()  # After Статья marker — accumulate lines


# ---------------------------------------------------------------------------
# Structural markers
# ---------------------------------------------------------------------------

_RAZDEL_RE = re.compile(r'^Раздел\s+[IVXLCDM]+[.\s]', re.UNICODE)
_GLAVA_RE  = re.compile(r'^Глава\s+\d+[\d.]*\.', re.UNICODE)
_STATYA_RE = re.compile(r'^Статья\s+(\d+(?:\.\d+)?)\.?\s*(.*)', re.UNICODE)

# ---------------------------------------------------------------------------
# Pass 1 — Editor-only noise patterns (КонсультантПлюс annotations)
#
# These are editorial annotations injected by the КонсультантПлюс database
# exporter. They carry zero legal content and are safe to remove.
#
# Applied BEFORE the tombstone detector (Pass 2) to ensure that parenthetical
# annotations containing "утратил силу" are dropped here, not mis-flagged as
# tombstones.
# ---------------------------------------------------------------------------

_NOISE_PATTERNS: list[re.Pattern[str]] = [
    # Change-tracking annotations — always parenthetical
    re.compile(r'^\(в\s+ред\.', re.UNICODE | re.IGNORECASE),
    re.compile(r'^\(п\.\s+[\d.]+\s+в\s+ред\.', re.UNICODE | re.IGNORECASE),
    re.compile(r'^\(пп\.\s+"[а-яёА-ЯЁ]"\s+в\s+ред\.', re.UNICODE | re.IGNORECASE),
    re.compile(r'^\(часть\s+\w+\s+(введена|в\s+ред)\.', re.UNICODE | re.IGNORECASE),
    re.compile(r'^\(введен\w*\s+Федеральным', re.UNICODE | re.IGNORECASE),
    re.compile(r'^\(статья\s+введена', re.UNICODE | re.IGNORECASE),
    re.compile(r'^\(пункт\s+введен', re.UNICODE | re.IGNORECASE),
    # КонсультантПлюс UI elements
    re.compile(r'^КонсультантПлюс:\s+примечание', re.UNICODE | re.IGNORECASE),
    re.compile(r'^Позиции\s+высших\s+судов\s+по\s+ст\.', re.UNICODE | re.IGNORECASE),
    # Distributor metadata (should already be in HEADER but can appear inline)
    re.compile(r'^Документ\s+предоставлен\s+КонсультантПлюс', re.UNICODE | re.IGNORECASE),
    re.compile(r'^www\.consultant\.ru', re.UNICODE | re.IGNORECASE),
    re.compile(r'^Дата\s+сохранения:', re.UNICODE | re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Pass 2 — Tombstone detector (legally meaningful status content)
#
# Applied ONLY to lines that survived Pass 1. Detects official repeal language
# that is part of the law text itself, not an editorial annotation.
#
# Examples that trigger this:
#   "Статья 7. Утратила силу. - Федеральный закон от 30.06.2006 N 90-ФЗ."
#   "Часть вторая утратила силу. - Федеральный закон от ..."
#   "Статья 175. Утратила силу с 1 сентября 2013 года."
# ---------------------------------------------------------------------------

_TOMBSTONE_RE = re.compile(r'[Уу]тратил[аи]?\s+силу', re.UNICODE)

# ---------------------------------------------------------------------------
# Part splitter
# ---------------------------------------------------------------------------

# Matches numbered parts: "1. Text", "2. Text" — the mandatory space after
# the period distinguishes from decimal article numbers like "19.1"
_NUMBERED_PART_RE = re.compile(r'^(\d+)\.\s+(.+)', re.UNICODE)

_SPLIT_THRESHOLD = 700  # chars — articles shorter than this stay as one chunk


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_noise(line: str) -> bool:
    """Return True if the line should be dropped by Pass 1 (editor noise)."""
    stripped = line.strip()
    return any(p.match(stripped) for p in _NOISE_PATTERNS)


def _is_tombstone_line(line: str) -> bool:
    """Return True if the line contains legal repeal language (Pass 2)."""
    return bool(_TOMBSTONE_RE.search(line))


def _split_into_parts(raw_text: str, is_tombstone: bool) -> list[RussianArticlePart]:
    """
    Split article body text into RussianArticlePart instances.

    Rules:
    1. Tombstone → always 1 part regardless of length or content.
    2. Short article (≤ SPLIT_THRESHOLD chars) → 1 part.
    3. Long article WITH numbered parts → split at "N. " boundaries.
       - Text before the first "N. " becomes the intro part (is_intro=True).
       - Each "N. " block becomes a part with its label as part_num.
    4. Long article WITHOUT numbered parts → 1 part (no split boundary found).

    Пункты (1) 2) 3)) and подпункты (а) б)) are NOT split boundaries —
    they stay inside their parent part to keep related list items together.
    """
    if is_tombstone or len(raw_text) <= _SPLIT_THRESHOLD:
        return [RussianArticlePart(part_num=None, text=raw_text.strip(), is_intro=False)]

    lines = raw_text.splitlines()

    # Find numbered-part boundary lines
    boundaries: list[tuple[int, int, str]] = []  # (line_index, part_num, rest_of_line)
    for idx, line in enumerate(lines):
        m = _NUMBERED_PART_RE.match(line.strip())
        if m:
            boundaries.append((idx, int(m.group(1)), m.group(2)))

    if not boundaries:
        # No numbered parts — single chunk even though text is long
        return [RussianArticlePart(part_num=None, text=raw_text.strip(), is_intro=False)]

    parts: list[RussianArticlePart] = []

    # Intro: lines before first boundary
    first_boundary_idx = boundaries[0][0]
    intro_lines = lines[:first_boundary_idx]
    intro_text = "\n".join(intro_lines).strip()
    if intro_text:
        parts.append(RussianArticlePart(part_num=None, text=intro_text, is_intro=True))

    # Numbered parts
    for i, (line_idx, part_num, first_line) in enumerate(boundaries):
        # Content of this part: from this boundary to the next (or end)
        if i + 1 < len(boundaries):
            next_line_idx = boundaries[i + 1][0]
            part_lines = [first_line] + [l.strip() for l in lines[line_idx + 1:next_line_idx]]
        else:
            part_lines = [first_line] + [l.strip() for l in lines[line_idx + 1:]]

        part_text = "\n".join(l for l in part_lines if l).strip()
        if part_text:
            parts.append(RussianArticlePart(part_num=part_num, text=part_text, is_intro=False))

    return parts if parts else [RussianArticlePart(part_num=None, text=raw_text.strip(), is_intro=False)]


def _flush_article(
    law_id: str,
    source_file: str,
    article_num: str,
    heading: str,
    razdel: str | None,
    glava: str,
    accumulated: list[str],
    article_position: int,
) -> RussianArticle:
    """
    Build a RussianArticle from accumulated lines.

    Two-pass processing:
    Pass 1: noise filter — drop КонсультантПлюс editorial annotations
    Pass 2: tombstone detector — flag articles with repeal language

    Ordering guarantee: article_position is always set by the caller from
    an explicit counter incremented only when this function is called.
    """
    is_tombstone = False
    clean_lines: list[str] = []
    skip_next = False  # flag for КонсультантПлюс note lines

    # Check heading for tombstone status (before processing body)
    if _is_tombstone_line(heading):
        is_tombstone = True

    for line in accumulated:
        # Handle КонсультантПлюс примечание: skip this line AND the next
        if skip_next:
            skip_next = False
            continue

        stripped = line.strip()
        if not stripped:
            clean_lines.append("")
            continue

        # Pass 1: editor noise
        if _is_noise(stripped):
            if re.match(r'^КонсультантПлюс:\s+примечание', stripped, re.IGNORECASE | re.UNICODE):
                skip_next = True
            continue

        # Pass 2: tombstone detector (runs only on lines that survived Pass 1)
        # Skip пункт lines (1) 2) 3)) — sub-items are not article-level status
        if not is_tombstone and not re.match(r'^\d+(?:\.\d+)?\)', stripped) and _is_tombstone_line(stripped):
            is_tombstone = True

        clean_lines.append(stripped)

    raw_text = "\n".join(clean_lines).strip()
    # Tombstone articles whose body is empty (repeal declared only in heading)
    # must still carry non-empty text so downstream indexing has content.
    if is_tombstone and not raw_text:
        raw_text = heading.strip()
    parts = _split_into_parts(raw_text, is_tombstone)

    return RussianArticle(
        law_id=law_id,
        article_num=article_num,
        heading=heading.strip(),
        razdel=razdel,
        glava=glava,
        parts=parts,
        raw_text=raw_text,
        is_tombstone=is_tombstone,
        article_position=article_position,
        source_file=source_file,
        parse_errors=[],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_law(metadata: LawMetadata, raw_text: str) -> ParseResult:
    """
    Parse all articles from a raw law text string.

    Args:
        metadata: LawMetadata produced by loader.load_law_file()
        raw_text: full file content as a string (UTF-16 decoded by loader)

    Returns:
        ParseResult with all articles in file order.
    """
    law_id = metadata.law_id
    source_file = metadata.source_file

    state = _State.HEADER
    current_razdel: str | None = None
    current_glava: str = ""

    # Accumulator for current article
    current_article_num: str = ""
    current_heading: str = ""
    accumulated: list[str] = []

    articles: list[RussianArticle] = []
    article_seq = 0  # explicit counter — sole source of article_position
    law_errors: list[str] = []

    lines = raw_text.splitlines()

    def flush() -> None:
        """Flush the current accumulated article into articles list."""
        nonlocal article_seq
        if not current_article_num:
            return
        article = _flush_article(
            law_id=law_id,
            source_file=source_file,
            article_num=current_article_num,
            heading=current_heading,
            razdel=current_razdel,
            glava=current_glava,
            accumulated=accumulated,
            article_position=article_seq,
        )
        articles.append(article)
        article_seq += 1

    for line in lines:
        stripped = line.strip()

        # ── Structural markers always checked regardless of state ──────────

        if _RAZDEL_RE.match(stripped):
            if state == _State.IN_ARTICLE:
                flush()
                accumulated.clear()
                current_article_num = ""
                current_heading = ""
            current_razdel = stripped
            current_glava = ""
            state = _State.IN_SECTION
            continue

        if _GLAVA_RE.match(stripped):
            if state == _State.IN_ARTICLE:
                flush()
                accumulated.clear()
                current_article_num = ""
                current_heading = ""
            current_glava = stripped
            state = _State.IN_CHAPTER
            continue

        m_statya = _STATYA_RE.match(stripped)
        if m_statya:
            if state == _State.IN_ARTICLE:
                flush()
                accumulated.clear()
            current_article_num = m_statya.group(1)
            current_heading = m_statya.group(2).strip()
            state = _State.IN_ARTICLE
            continue

        # ── Accumulate article body ────────────────────────────────────────

        if state == _State.IN_ARTICLE:
            accumulated.append(stripped)

        # ── HEADER state: discard everything ──────────────────────────────
        # (implicit — nothing happens for HEADER / IN_SECTION / IN_CHAPTER lines
        #  that are not structural markers)

    # Flush the final article
    if state == _State.IN_ARTICLE and current_article_num:
        flush()

    tombstone_count = sum(1 for a in articles if a.is_tombstone)
    all_errors = law_errors + [e for a in articles for e in a.parse_errors]

    log.info(
        "parser.done law_id=%r articles=%d tombstones=%d errors=%d",
        law_id, len(articles), tombstone_count, len(all_errors),
    )

    return ParseResult(
        metadata=metadata,
        articles=articles,
        article_count=len(articles),
        tombstone_count=tombstone_count,
        parse_error_count=len(all_errors),
        parse_errors=law_errors,
    )
