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
}


def _heading_penalty(text: str) -> float:
    """Return score penalty for short heading chunks that lack verb content."""
    value = (text or "").strip()
    if not value:
        return 0.0
    words = re.findall(r"\w+", value, flags=re.UNICODE)
    if len(value) >= 80 or len(words) > 8:
        return 0.0
    if "." in value:
        return 0.0
    if any(hint in value.lower() for hint in _HEADING_VERB_HINTS):
        return 0.0
    return 0.35


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
        timeout_ms=300,
    )

    # fail-open: scores is None on timeout/exception
    if scores is None:
        return items

    remainder = items[len(subset):]

    # sort by (cross_encoder_score - heading_penalty) descending
    # tie-break by original index to keep stable ordering
    ranked = sorted(
        enumerate(zip(subset, scores)),
        key=lambda entry: (
            -(float(entry[1][1]) - _heading_penalty(entry[1][0].text or "")),
            entry[0],
        ),
    )

    return [item for _, (item, _) in ranked] + remainder
