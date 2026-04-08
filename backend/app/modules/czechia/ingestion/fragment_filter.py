"""
Filtering rules for law_fragments before vector ingestion.

Only fragments with meaningful text are ingested.  Structural placeholder
nodes (pure hierarchy markers, empty citace fields) are dropped from
vectorization but remain referenceable via their IRI in the relation index.

The filter is intentionally simple and configurable.  Adjust MIN_TEXT_LENGTH
to change sensitivity without touching any other part of the pipeline.

Phase 2 extension:
  - Add a FilterStrategy enum (STRICT / PERMISSIVE) and pass it to should_ingest()
    if domain-specific rules are needed (e.g. keep all par_* nodes regardless
    of text length for graph completeness).
"""

from __future__ import annotations

from dataclasses import dataclass

# Minimum character count for a fragment's text to be considered meaningful.
# Value 3 allows short but real citations like "§ 1" while dropping empty strings.
MIN_TEXT_LENGTH: int = 3


@dataclass(frozen=True)
class FilterResult:
    accepted: bool
    reason: str  # "ok" | "empty_text" | "text_too_short"


_ACCEPTED = FilterResult(accepted=True, reason="ok")
_EMPTY = FilterResult(accepted=False, reason="empty_text")
_TOO_SHORT = FilterResult(accepted=False, reason="text_too_short")


def should_ingest(fragment: dict) -> FilterResult:
    """
    Return FilterResult(accepted=True) if the fragment should be vectorized.

    Rules applied in order:
      1. text field must be present and non-empty after stripping
      2. text must be at least MIN_TEXT_LENGTH characters

    Dropped fragments are still referenceable via fragment_id in the
    relation index — they are not lost, just not vectorized.
    """
    text = (fragment.get("text") or "").strip()
    if not text:
        return _EMPTY
    if len(text) < MIN_TEXT_LENGTH:
        return _TOO_SHORT
    return _ACCEPTED
