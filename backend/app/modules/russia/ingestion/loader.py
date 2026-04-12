"""
Loader for Russian law files in UTF-16 LE format (KonsultantPlus export).

Responsibilities:
- Open and decode UTF-16 LE files (BOM handled automatically by Python)
- Extract law-level metadata from the file header (~first 50 lines)
- Derive a canonical law_id from the filename
- Return (LawMetadata, raw_text) for the parser

Deliberately does NOT parse articles — that is the parser's job.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from app.modules.russia.ingestion.schemas import LawMetadata

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Law ID derivation — static map from filename substring → (law_id, short)
# Matched in order; first match wins.
# ---------------------------------------------------------------------------
_LAW_ID_MAP: list[tuple[str, str, str]] = [
    # (filename substring pattern, law_id, short)
    # GK parts must be matched before generic "гражданский кодекс"
    ("часть первая",                      "local:ru/gk/1",   "ГК РФ ч.1"),
    ("часть вторая",                      "local:ru/gk/2",   "ГК РФ ч.2"),
    ("часть третья",                      "local:ru/gk/3",   "ГК РФ ч.3"),
    ("часть четвертая",                   "local:ru/gk/4",   "ГК РФ ч.4"),
    # NK parts
    ("налоговый кодекс.*часть первая",    "local:ru/nk/1",   "НК РФ ч.1"),
    ("налоговый кодекс.*часть вторая",    "local:ru/nk/2",   "НК РФ ч.2"),
    # Single-part codes — matched by distinctive word
    ("семейный кодекс",                   "local:ru/sk",     "СК РФ"),
    ("трудовой кодекс",                   "local:ru/tk",     "ТК РФ"),
    ("гражданский процессуальный кодекс", "local:ru/gpk",    "ГПК РФ"),
    ("арбитражный процессуальный кодекс", "local:ru/apk",    "АПК РФ"),
    ("кодекс административного судопроиз","local:ru/kas",    "КАС РФ"),
    ("кодекс.*административных правонар", "local:ru/koap",   "КоАП РФ"),
    ("уголовно-процессуальный кодекс",    "local:ru/upk",    "УПК РФ"),
    ("уголовно-исполнительный кодекс",    "local:ru/uik",    "УИК РФ"),
    ("уголовный кодекс",                  "local:ru/uk",     "УК РФ"),
    ("жилищный кодекс",                   "local:ru/zhk",    "ЖК РФ"),
    ("земельный кодекс",                  "local:ru/zk",     "ЗК РФ"),
    ("водный кодекс",                     "local:ru/vk",     "ВК РФ"),
    ("воздушный кодекс",                  "local:ru/vzk",    "ВзК РФ"),
    ("градостроительный кодекс",          "local:ru/grk",    "ГрК РФ"),
    ("бюджетный кодекс",                  "local:ru/bk",     "БК РФ"),
    ("таможенный кодекс",                 "local:ru/tk_eaes","ТК ЕАЭС"),
    ("конституция",                       "local:ru/konst",  "Конституция РФ"),
    # Federal laws by number — extracted from filename if present
    # Matched as fallback for ФЗ files that don't have a code name
]

# Regex to extract NN-ФЗ law number from filename or header
_LAW_NUMBER_RE = re.compile(r'N\s+(\d+[-–]\s*(?:ФЗ|ФКЗ|ФЗ-\d+))', re.IGNORECASE | re.UNICODE)
# Regex to extract date from header (DD.MM.YYYY format)
_LAW_DATE_RE = re.compile(r'\b(\d{2}\.\d{2}\.\d{4})\b')
# Regex to extract quoted title from file first line, e.g. "Трудовой кодекс..."
_QUOTED_TITLE_RE = re.compile(r'["\u201c\u201e](.+?)["\u201d\u201f]', re.UNICODE)


def _derive_law_id(filename: str) -> tuple[str, str]:
    """
    Return (law_id, law_short) by matching filename against _LAW_ID_MAP.

    Matching is case-insensitive on the lowercased filename. First match wins.
    Falls back to ('local:ru/unknown', 'Unknown') with a warning if no match.
    """
    lower = filename.lower()
    for pattern, law_id, short in _LAW_ID_MAP:
        if re.search(pattern, lower, re.IGNORECASE | re.UNICODE):
            return law_id, short

    log.warning("loader.law_id_unknown filename=%r — using fallback", filename)
    # Use filename stem as a last-resort ID so data is not silently lost
    stem = Path(filename).stem[:40].replace(" ", "_").lower()
    return f"local:ru/unknown/{stem}", "Unknown"


def _extract_header_metadata(lines: list[str]) -> tuple[str, str | None, str | None]:
    """
    Scan the first 60 lines of the file for law title, number, and date.

    Returns (law_title, law_number, law_date).
    law_title: best available title string (quoted title or uppercase heading)
    law_number: e.g. "197-ФЗ" or None
    law_date: e.g. "30.12.2001" or None
    """
    law_title = ""
    law_number: str | None = None
    law_date: str | None = None

    header_lines = lines[:60]
    header_text = "\n".join(header_lines)

    # Try quoted title first (e.g. "Трудовой кодекс Российской Федерации")
    m = _QUOTED_TITLE_RE.search(header_text)
    if m:
        law_title = m.group(1).strip()

    # Extract law number (N NNN-ФЗ)
    m_num = _LAW_NUMBER_RE.search(header_text)
    if m_num:
        law_number = m_num.group(1).strip().replace(" ", "").replace("–", "-")

    # Extract earliest date found in header
    dates = _LAW_DATE_RE.findall(header_text)
    if dates:
        law_date = dates[0]

    # Fallback title: first all-caps line that looks like a law name
    if not law_title:
        for line in header_lines:
            stripped = line.strip()
            if stripped and stripped == stripped.upper() and len(stripped) > 10 and len(stripped) < 120:
                if "КОДЕКС" in stripped or "ЗАКОН" in stripped or "КОНСТИТУЦИЯ" in stripped:
                    law_title = stripped.title()
                    break

    return law_title, law_number, law_date


def load_law_file(path: str | Path) -> tuple[LawMetadata, str]:
    """
    Load a single Russian law file in UTF-16 LE format.

    Returns:
        (LawMetadata, raw_text) where raw_text is the complete file content as a string.

    The returned raw_text still contains all lines including header, noise, and article text.
    The parser is responsible for consuming raw_text and producing structured articles.

    Raises:
        FileNotFoundError: if path does not exist
        UnicodeDecodeError: if file is not valid UTF-16 (should not happen for corpus files)
    """
    path = Path(path)
    filename = path.name

    log.debug("loader.loading path=%r", str(path))

    with open(path, encoding="utf-16") as fh:
        raw_text = fh.read()

    lines = raw_text.splitlines()
    law_id, law_short = _derive_law_id(filename)
    law_title, law_number, law_date = _extract_header_metadata(lines)

    if not law_title:
        # Last resort: use the short code
        law_title = law_short
        log.warning("loader.title_not_found filename=%r law_id=%r", filename, law_id)

    metadata = LawMetadata(
        law_id=law_id,
        law_title=law_title,
        law_short=law_short,
        law_number=law_number,
        law_date=law_date,
        source_file=filename,
        ingest_timestamp=datetime.now(timezone.utc).isoformat(),
    )

    log.info(
        "loader.loaded law_id=%r title=%r number=%r date=%r lines=%d",
        law_id, law_title, law_number, law_date, len(lines),
    )

    return metadata, raw_text
