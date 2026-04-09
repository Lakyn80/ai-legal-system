from typing import List

_SYSTEM_TAGS = {"irrelevant_query", "no_result", "clarification"}


def filter_by_score(results: List, min_score: float = 0.9) -> List:
    """
    Filter results below min_score.
    System responses (irrelevant_query, no_result, clarification) always pass through.
    """
    return [
        r for r in results
        if r.score >= min_score or bool(set(getattr(r, "tags", []) or []) & _SYSTEM_TAGS)
    ]
