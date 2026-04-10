from __future__ import annotations

import logging
from threading import Lock

from app.modules.common.reranker.provider import BaseRerankerProvider

log = logging.getLogger(__name__)

# bge-reranker-base: ~280 MB, ~30-80 ms/batch on CPU (vs ~1 GB for large)
_MODEL_NAME = "BAAI/bge-reranker-base"

_instance: BGERerankerProvider | None = None
_instance_lock = Lock()
_init_failed = False  # set True on first failed init — skip all future attempts


class BGERerankerProvider(BaseRerankerProvider):
    """
    Cross-encoder reranker backed by BAAI/bge-reranker-base.

    Lazy-loaded on first call.  Thread-safe singleton.
    Falls back (raises) so callers can apply fail-open logic.
    """

    def __init__(self) -> None:
        from sentence_transformers import CrossEncoder
        self._model = CrossEncoder(_MODEL_NAME, device="cpu")
        log.info("reranker.bge.loaded model=%s", _MODEL_NAME)

    def score(self, query: str, documents: list[str]) -> list[float]:
        pairs = [(query, doc) for doc in documents]
        scores = self._model.predict(pairs)
        return [float(s) for s in scores]


def get_bge_provider() -> BGERerankerProvider:
    """
    Return the singleton BGERerankerProvider.
    Raises RuntimeError if model init previously failed (fail-fast after first error).
    """
    global _instance, _init_failed

    if _init_failed:
        raise RuntimeError("BGERerankerProvider init previously failed — skipping")

    if _instance is not None:
        return _instance

    with _instance_lock:
        if _instance is None:
            try:
                _instance = BGERerankerProvider()
            except Exception as exc:
                _init_failed = True
                raise RuntimeError(f"BGERerankerProvider init failed: {exc}") from exc

    return _instance
