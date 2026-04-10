from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

log = logging.getLogger(__name__)

_MAX_TEXT_CHARS = 768
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reranker")


def rerank(
    query: str,
    results: list,
    candidate_limit: int = 10,
    timeout_ms: int = 300,
) -> list:
    """
    Reorder `results` by cross-encoder relevance score.

    - len(results) < 2 → return unchanged
    - only first `candidate_limit` items are scored; rest appended unchanged
    - text truncated to 768 chars before scoring
    - original result.score is NOT overwritten
    - timeout or exception → return original order (fail-open)
    """
    if len(results) < 2:
        return results

    subset = results[:candidate_limit]
    remainder = results[candidate_limit:]
    documents = [(r.text or "")[:_MAX_TEXT_CHARS] for r in subset]

    scores = _score_with_timeout(query, documents, timeout_ms)
    if scores is None:
        return results  # fail-open

    ranked = sorted(zip(subset, scores), key=lambda p: p[1], reverse=True)
    return [item for item, _ in ranked] + remainder


def score_with_fallback(
    query: str,
    results: list,
    candidate_limit: int = 10,
    timeout_ms: int = 300,
) -> tuple[list, list[float] | None]:
    """
    Like rerank() but returns (subset, scores_or_None).

    Useful when the caller needs the raw scores to apply domain-specific
    penalties before final sorting (e.g. heading penalty for Czech law).

    Returns:
        (subset, scores) where subset = results[:candidate_limit]
        scores is None on timeout/failure (caller should return original order)
    """
    if len(results) < 2:
        return results, None

    subset = results[:candidate_limit]
    documents = [(r.text or "")[:_MAX_TEXT_CHARS] for r in subset]

    scores = _score_with_timeout(query, documents, timeout_ms)
    return subset, scores


def _score_with_timeout(query: str, documents: list[str], timeout_ms: int) -> list[float] | None:
    t0 = time.monotonic()
    future = _EXECUTOR.submit(_score, query, documents)
    timeout_sec = timeout_ms / 1000.0

    try:
        scores = future.result(timeout=timeout_sec)
    except FuturesTimeoutError:
        elapsed_ms = (time.monotonic() - t0) * 1000
        log.warning(
            "reranker.timeout elapsed_ms=%.1f timeout_ms=%d — returning original order",
            elapsed_ms, timeout_ms,
        )
        future.cancel()
        return None
    except Exception as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        log.warning(
            "reranker.fallback elapsed_ms=%.1f reason=%s — returning original order",
            elapsed_ms, exc,
        )
        return None

    elapsed_ms = (time.monotonic() - t0) * 1000
    log.debug("reranker.scored candidates=%d elapsed_ms=%.1f", len(documents), elapsed_ms)
    return scores


def _score(query: str, documents: list[str]) -> list[float]:
    from app.modules.common.reranker.providers.bge import get_bge_provider
    return get_bge_provider().score(query, documents)
