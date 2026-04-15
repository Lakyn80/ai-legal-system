"""
BM25 sparse retriever for the configured Russian Qdrant collection.

Uses RussianBM25Encoder and IDFTable from the ingestion pipeline so that
query and document token spaces are always identical.

The IDF table is loaded lazily on first search() call. If the checkpoint
file does not exist, search() returns an empty list and logs a warning —
the system degrades gracefully to dense-only.

Collection: russian_laws_v1
Named vector: "sparse"  (SparseVectorParams — BM25)

Env override:
    RUSSIAN_IDF_CHECKPOINT_PATH  — path to IDFTable JSON
                                   (default: storage/idf_russian_laws_v1.json)

Does NOT:
  - Call any LLM
  - Import ingestion modules at module level (lazy import inside methods)
  - Perform dense retrieval
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.modules.russia.retrieval.schemas import RussianSearchResult

DEFAULT_COLLECTION_NAME = "russian_laws_v1"
_SPARSE_VECTOR_NAME = "sparse"
_QDRANT_TIMEOUT = 30

_IDF_CHECKPOINT_PATH = Path(
    os.environ.get("RUSSIAN_IDF_CHECKPOINT_PATH", "storage/idf_russian_laws_v1.json")
)

log = logging.getLogger(__name__)


class RussianSparseRetriever:
    """
    BM25 sparse search against russian_laws_v1.

    Lazy-loads the RussianBM25Encoder from the IDF checkpoint on first call.
    Thread-safe after initialization (IDFTable is immutable, encoder is stateless).

    Usage:
        retriever = RussianSparseRetriever(url="http://qdrant:6333")
        results = retriever.search("расторжение трудового договора", law_id="local:ru/tk", top_k=10)
    """

    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        idf_checkpoint_path: Path | None = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        self._client = QdrantClient(url=url, api_key=api_key, timeout=_QDRANT_TIMEOUT)
        self._idf_path = idf_checkpoint_path or _IDF_CHECKPOINT_PATH
        self._collection_name = collection_name
        self._encoder = None       # lazy init
        self._encoder_attempted = False

    def search(
        self,
        query: str,
        law_id: str | None = None,
        top_k: int = 10,
    ) -> list[RussianSearchResult]:
        """
        Encode query with BM25 and search the sparse index.

        Args:
            query:   Free-text query in Russian
            law_id:  Optional canonical IRI to restrict results to one law
            top_k:   Maximum number of results to return

        Returns:
            List of RussianSearchResult in score-descending order.
            Empty list if IDF checkpoint unavailable or query encodes to empty.
        """
        if not query.strip() or top_k <= 0:
            return []

        encoder = self._get_encoder()
        if encoder is None:
            return []

        indices, values = encoder.encode_query(query)
        if not indices:
            log.debug("sparse_retriever.empty_query_vector query=%r", query[:60])
            return []

        query_filter = _build_law_filter(law_id)

        try:
            response = self._client.query_points(
                collection_name=self._collection_name,
                query=qm.SparseVector(
                    indices=list(indices),
                    values=[float(v) for v in values],
                ),
                using=_SPARSE_VECTOR_NAME,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            log.error("sparse_retriever.search_failed query=%r err=%s", query[:60], exc)
            return []

        results = [_point_to_result(p) for p in response.points]

        log.debug(
            "sparse_retriever.search query=%r law_id=%r top_k=%d results=%d",
            query[:60], law_id, top_k, len(results),
        )
        return results

    # ── internals ─────────────────────────────────────────────────────────────

    def _get_encoder(self):
        """Lazy-load RussianBM25Encoder from IDF checkpoint."""
        if self._encoder_attempted:
            return self._encoder

        self._encoder_attempted = True

        if not self._idf_path.exists():
            log.warning(
                "sparse_retriever: IDF checkpoint not found: %s — "
                "sparse search disabled (re-ingest with --idf-checkpoint to enable)",
                self._idf_path.resolve(),
            )
            return None

        try:
            from app.modules.russia.ingestion.sparse_encoder import (  # noqa: PLC0415
                IDFTable,
                RussianBM25Encoder,
            )
            idf_table = IDFTable.load(self._idf_path)
            self._encoder = RussianBM25Encoder(idf_table)
            log.info(
                "sparse_retriever: BM25 encoder ready: vocab=%d avg_dl=%.1f",
                idf_table.vocab_size,
                idf_table.avg_dl,
            )
        except Exception as exc:
            log.error("sparse_retriever: failed to load IDF table: %s", exc)

        return self._encoder


# ── helpers ────────────────────────────────────────────────────────────────────

def _build_law_filter(law_id: str | None) -> qm.Filter | None:
    if not law_id:
        return None
    return qm.Filter(
        must=[qm.FieldCondition(key="law_id", match=qm.MatchValue(value=law_id))]
    )


def _point_to_result(point) -> RussianSearchResult:
    p = point.payload or {}
    return RussianSearchResult(
        score=float(point.score),
        chunk_id=str(p.get("chunk_id", "")),
        law_id=str(p.get("law_id", "")),
        law_short=str(p.get("law_short", "")),
        article_num=str(p.get("article_num", "")),
        article_heading=str(p.get("article_heading", "")),
        part_num=p.get("part_num"),
        chunk_index=int(p.get("chunk_index", 0)),
        razdel=p.get("razdel"),
        glava=str(p.get("glava", "")),
        text=str(p.get("text", "")),
        fragment_id=str(p.get("fragment_id", "")),
        source_type=str(p.get("source_type", "article")),
        is_tombstone=bool(p.get("is_tombstone", False)),
        source_file=str(p.get("source_file", "")),
    )
