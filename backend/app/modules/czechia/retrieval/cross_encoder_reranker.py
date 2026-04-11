"""
Czech law cross-encoder reranker shim.

Delegates provider lifecycle, lazy init, timeout and fail-open to
app.modules.common.reranker.service.  Adds Czech-law specific heading
penalty on top of the raw cross-encoder scores before final sorting.

Heading penalty rationale:
  Short all-caps fragments (section headings like "DOVOLENÁ", "VÝPOVĚĎ")
  score artificially high on pure semantic relevance because the query
  often contains those exact words.  We penalise them so substantive
  paragraph text wins over bare headings.
"""
from __future__ import annotations

import re

from app.modules.common.reranker import service as _reranker_service
from app.modules.czechia.retrieval.schemas import EvidencePackItem

_HEADING_VERB_HINTS = {
    "je", "jsou", "musi", "musí", "muze", "může", "lze",
    "byla", "byly", "byl", "cini", "činí", "obsahuje", "obsahovat",
    "skonci", "skončí", "zacina", "začíná", "konci", "končí", "upravuje",
    "má", "ma", "vzniká", "vznika", "zaniká", "zanika", "trvá", "trva",
}

# Matches numbered entries from derogation/amendment schedules, e.g.:
#   "1. zákon č. 65/1965 Sb., zákoník práce ,"
#   "16. nařízení vlády č. 108/1994 Sb., ..."
#   "21. Část první zákona č. 367/2000 Sb., ..."  ← part-of-act entries
# These are index lines in a law's derogation schedule — not substantive text.
_INDEX_LINE_RE = re.compile(
    r"^\d{1,3}\.\s+(?:(?:část|hlava|díl)\s+\w+\s+)?(?:z[aá]kon|na[rř][íi]zen[íi]|vyhl[áa][šs]ka|sd[eě]len[íi])",
    re.IGNORECASE | re.UNICODE,
)
_SECTION_HEADING_RE = re.compile(
    r"^(?:část|hlava|díl|oddíl|pododdíl|kapitola)\b",
    re.IGNORECASE | re.UNICODE,
)
_AMENDMENT_LINE_RE = re.compile(
    r"(?:z[aá]kon|na[rř][íi]zen[íi](?:\s+vl[aá]dy)?|vyhl[áa][šs]ka|sd[eě]len[íi])\s+č\.",
    re.IGNORECASE | re.UNICODE,
)


def _chunk_penalty(text: str) -> float:
    """
    Return total score penalty for non-substantive chunk types.

    Penalties applied (cumulative):
    - 0.40  short heading without verb content  (e.g. "DOVOLENÁ", "VÝPOVĚĎ")
    - 0.55  numbered law-reference index line    (e.g. "1. zákon č. 65/1965 Sb.,")
    - 0.45  section / chapter heading            (e.g. "HLAVA II")
    - 0.35  short amendment line                 (e.g. "zákon č. 65/1965 Sb.")
    """
    value = (text or "").strip()
    if not value:
        return 0.0

    penalty = 0.0
    words = re.findall(r"\w+", value, flags=re.UNICODE)

    # ── index-line penalty ────────────────────────────────────────────────────
    # Numbered entries from derogation/amendment schedules rank artificially
    # high on BM25 because they contain many law names.  They are never the
    # answer to an informational query.
    if _INDEX_LINE_RE.match(value):
        penalty += 0.55
    elif _AMENDMENT_LINE_RE.search(value) and len(value) < 140:
        penalty += 0.35

    if _SECTION_HEADING_RE.match(value):
        penalty += 0.45

    # ── heading penalty ───────────────────────────────────────────────────────
    if len(value) < 120 and len(words) <= 12 and not re.search(r"[.!?;:]", value):
        if not any(hint in value.lower() for hint in _HEADING_VERB_HINTS):
            penalty += 0.40
            if _is_all_caps_heading(value):
                penalty += 0.15

    return min(penalty, 0.90)


def _is_all_caps_heading(text: str) -> bool:
    letters = re.sub(r"[^A-Za-zÀ-ž]", "", text, flags=re.UNICODE)
    return bool(letters) and letters == letters.upper()


def rerank(query: str, items: list[EvidencePackItem], top_n: int = 10) -> list[EvidencePackItem]:
    """
    Rerank `items` using cross-encoder + heading penalty.

    - Timeout / model failure → return original order (fail-open via common service)
    - Does NOT overwrite item.score
    - Only reorders top_n candidates; rest are appended unchanged
    """
    if len(items) < 2:
        return items

    subset, scores = _reranker_service.score_with_fallback(
        query=query,
        results=items,
        candidate_limit=top_n,
        timeout_ms=1200,
    )

    # fail-open: scores is None on timeout/exception
    if scores is None:
        return items

    remainder = items[len(subset):]

    # sort by (cross_encoder_score - chunk_penalty) descending
    # tie-break by original index to keep stable ordering
    ranked = sorted(
        enumerate(zip(subset, scores)),
        key=lambda entry: (
            -(float(entry[1][1]) - _chunk_penalty(entry[1][0].text or "")),
            entry[0],
        ),
    )

    return [item for _, (item, _) in ranked] + remainder
