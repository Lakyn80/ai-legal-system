from __future__ import annotations

import re
import unicodedata
from typing import Any

LAW_REFERENCE_MAP: dict[str, str] = {
    "zákoník práce": "local:sb/2006/262",
    "zakonik prace": "local:sb/2006/262",
    "262/2006": "local:sb/2006/262",
    "trestní zákoník": "local:sb/2009/40",
    "trestni zakonik": "local:sb/2009/40",
    "40/2009": "local:sb/2009/40",
    "občanský zákoník": "local:sb/2012/89",
    "obcansky zakonik": "local:sb/2012/89",
    "89/2012": "local:sb/2012/89",
}

_PARAGRAPH_RE = re.compile(r"(?:§\s*|paragraf\s+)(\d+)", re.IGNORECASE)
_PARAGRAPH_SYMBOL_NORMALIZE_RE = re.compile(r"§\s*(\d+)", re.IGNORECASE)
_PARAGRAPH_WORD_NORMALIZE_RE = re.compile(r"\bparagraf\s+(\d+)\b", re.IGNORECASE)
_LAW_NUMBER_RE = re.compile(r"\b(\d{1,4})\s*/\s*(\d{4})\b")
_WHITESPACE_RE = re.compile(r"\s+")

def parse_query(query: str) -> dict[str, Any]:
    original_query = query or ""
    normalized_query = _normalize_query(original_query)
    paragraph = _extract_paragraph(normalized_query)
    law_id = _extract_law_id(normalized_query)

    filters: dict[str, str] = {}
    if law_id:
        filters["document_id"] = law_id

    return {
        "original_query": original_query,
        "normalized_query": normalized_query,
        "paragraph": paragraph,
        "law_id": law_id,
        "filters": filters,
    }


def _normalize_query(query: str) -> str:
    text = (query or "").strip().lower()
    text = _LAW_NUMBER_RE.sub(lambda m: f"{m.group(1)}/{m.group(2)}", text)
    text = _PARAGRAPH_WORD_NORMALIZE_RE.sub(lambda m: f"§ {m.group(1)}", text)
    text = _PARAGRAPH_SYMBOL_NORMALIZE_RE.sub(lambda m: f"§ {m.group(1)}", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _extract_paragraph(normalized_query: str) -> int | None:
    match = _PARAGRAPH_RE.search(normalized_query)
    if not match:
        return None
    return int(match.group(1))


def _extract_law_id(normalized_query: str) -> str | None:
    numeric_match = _LAW_NUMBER_RE.search(normalized_query)
    if numeric_match:
        law_number = numeric_match.group(1)
        law_year = numeric_match.group(2)
        numeric_key = f"{law_number}/{law_year}"
        return LAW_REFERENCE_MAP.get(numeric_key, f"local:sb/{law_year}/{law_number}")

    folded_query = _fold_text(normalized_query)
    for alias in sorted(_FOLDED_LAW_REFERENCE_MAP.keys(), key=len, reverse=True):
        if alias in folded_query:
            return _FOLDED_LAW_REFERENCE_MAP[alias]

    return None


def _fold_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return _WHITESPACE_RE.sub(" ", folded.lower()).strip()


_FOLDED_LAW_REFERENCE_MAP: dict[str, str] = {
    _fold_text(alias): law_id
    for alias, law_id in LAW_REFERENCE_MAP.items()
}
