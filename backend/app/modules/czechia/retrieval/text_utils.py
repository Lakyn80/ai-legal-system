from __future__ import annotations

import re
import unicodedata

_WS_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.UNICODE)
_PARAGRAPH_RE = re.compile(r"§+\s*(\d+[a-z]?)", re.IGNORECASE)
_FRAGMENT_PARAGRAPH_RE = re.compile(r"/par_(\d+[a-z]?)", re.IGNORECASE)
_LAW_IRI_RE = re.compile(r"^local:sb/(\d{4})/(\d+)$")


def collapse_whitespace(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return collapse_whitespace(ascii_text)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalize_text(text))


def unique_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def law_ref_to_iri(number: str, year: str) -> str:
    return f"local:sb/{year}/{number}"


def parse_law_iri(law_iri: str) -> tuple[str | None, str | None]:
    match = _LAW_IRI_RE.match((law_iri or "").strip())
    if not match:
        return None, None
    return match.group(2), match.group(1)


def extract_paragraphs_from_text(text: str) -> list[str]:
    return unique_preserve([match.group(1) for match in _PARAGRAPH_RE.finditer(text or "")])


def extract_paragraphs_from_payload(payload: dict) -> list[str]:
    values: list[str] = []
    payload_paragraph = payload.get("paragraph")
    if payload_paragraph not in (None, ""):
        values.append(str(payload_paragraph))
    values.extend(extract_paragraphs_from_text(str(payload.get("text", ""))))
    fragment_id = str(payload.get("fragment_id", ""))
    for match in _FRAGMENT_PARAGRAPH_RE.finditer(fragment_id):
        values.append(match.group(1))
    return unique_preserve(values)


def pick_primary_paragraph(payload: dict) -> str | None:
    paragraphs = extract_paragraphs_from_payload(payload)
    if paragraphs:
        return paragraphs[0]
    return None


def overlap_ratio(query_tokens: list[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    query_set = set(query_tokens)
    if not query_set:
        return 0.0
    text_set = set(tokenize(text))
    if not text_set:
        return 0.0
    return len(query_set & text_set) / len(query_set)
