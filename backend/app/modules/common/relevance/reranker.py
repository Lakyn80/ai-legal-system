from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

# Passthrough stub — CzechLawReranker inside the retrieval pipeline handles re-ranking.
# warmup_reranker() eagerly loads the BGE cross-encoder in a background thread so that
# the first real query does not hit a 5-second cold-start timeout.


def warmup_reranker() -> None:
    """Trigger BGE model load in a background thread at startup."""

    def _load() -> None:
        try:
            from app.modules.common.reranker.providers.bge import get_bge_provider
            provider = get_bge_provider()
            # Run one dummy inference so JIT / tensor init is also done.
            provider.score("warmup", ["test"])
            log.info("reranker.warmup.done")
        except Exception as exc:
            log.warning("reranker.warmup.failed reason=%s", exc)

    t = threading.Thread(target=_load, name="reranker-warmup", daemon=True)
    t.start()
    log.info("reranker.warmup.started")


def rerank(query: str, results: list) -> list:
    return results
