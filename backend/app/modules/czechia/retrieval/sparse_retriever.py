"""
BM25 sparse retriever for the czech_laws_v2 Qdrant collection.

Uses the same CzechBM25Encoder and IDFTable as the ingestion pipeline to
guarantee that query and document token spaces are identical.

The IDF table is loaded lazily on first retrieval call.  If the checkpoint
file does not exist (e.g. before the first ingestion run), retrieve() returns
an empty list and logs a warning — the system degrades gracefully to dense-only.

Collection: czech_laws_v2
Named vector: "sparse"  (SparseVectorParams — BM25)

Env override:
    IDF_CHECKPOINT_PATH   path to IDFTable JSON   (default: storage/idf_czech_laws_v2.json)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http import models

_COLLECTION = "czech_laws_v2"
_SPARSE_VECTOR_NAME = "sparse"
_QDRANT_TIMEOUT = 30
_IDF_CHECKPOINT_PATH = Path(
    os.environ.get("IDF_CHECKPOINT_PATH", "storage/idf_czech_laws_v2.json")
)

log = logging.getLogger(__name__)


class CzechLawSparseRetriever:
    """
    Retrieves candidate chunks using BM25 sparse vectors stored in czech_laws_v2.

    Lazy-loads the CzechBM25Encoder from the IDF checkpoint on first call.
    Thread-safe after initialization (IDFTable is immutable, encoder is stateless).
    """

    def __init__(self, url: str, api_key: str | None = None) -> None:
        self.url = url
        self.api_key = api_key
        self._client = QdrantClient(
            url=url,
            api_key=api_key,
            timeout=_QDRANT_TIMEOUT,
        )
        self._encoder = None   # lazy init — set on first retrieve() call
        self._encoder_init_attempted = False

    # ── public ────────────────────────────────────────────────────────────────

    def retrieve(
        self,
        query_text: str,
        law_iris: list[str] | None = None,
        top_k: int = 20,
    ) -> list[dict]:
        """
        Encode query_text with BM25 and query the sparse index.

        Returns list of payload dicts with "_sparse_score" key.
        Returns [] if IDF checkpoint is unavailable or query encodes to empty.
        """
        if not query_text or top_k <= 0:
            return []

        encoder = self._get_encoder()
        if encoder is None:
            return []

        indices, values = encoder.encode_query(query_text)
        if not indices:
            return []

        try:
            response = self._client.query_points(
                collection_name=_COLLECTION,
                query=models.SparseVector(
                    indices=list(indices),
                    values=[float(v) for v in values],
                ),
                using=_SPARSE_VECTOR_NAME,
                query_filter=_build_law_filter(law_iris),
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            log.error("czech sparse retrieval failed: %s", exc)
            return []

        return [_point_to_payload(h) for h in response.points]

    # ── internals ─────────────────────────────────────────────────────────────

    def _get_encoder(self):
        """
        Lazy-load CzechBM25Encoder from IDF checkpoint.
        Returns None if checkpoint does not exist or loading fails.
        """
        if self._encoder_init_attempted:
            return self._encoder

        self._encoder_init_attempted = True

        if not _IDF_CHECKPOINT_PATH.exists():
            log.warning(
                "IDF checkpoint not found: %s — sparse retrieval disabled "
                "(run ingestion with FORCE_REBUILD_IDF=1 to build it)",
                _IDF_CHECKPOINT_PATH.resolve(),
            )
            return None

        try:
            from app.modules.czechia.ingestion.sparse_encoder import (
                CzechBM25Encoder,
                IDFTable,
            )
            idf_table = IDFTable.load(_IDF_CHECKPOINT_PATH)
            self._encoder = CzechBM25Encoder(idf_table)
            log.info(
                "BM25 encoder ready: vocab=%d avg_dl=%.1f",
                idf_table.vocab_size,
                idf_table.avg_dl,
            )
        except Exception as exc:
            log.error("Failed to load IDF table from %s: %s", _IDF_CHECKPOINT_PATH, exc)

        return self._encoder


# ── helpers ────────────────────────────────────────────────────────────────────

def _build_law_filter(law_iris: list[str] | None) -> models.Filter | None:
    if not law_iris:
        return None
    return models.Filter(
        must=[
            models.FieldCondition(
                key="law_iri",
                match=models.MatchAny(any=law_iris),
            )
        ]
    )


def _point_to_payload(point) -> dict:
    payload = dict(point.payload or {})
    payload["_sparse_score"] = float(point.score)
    return payload
