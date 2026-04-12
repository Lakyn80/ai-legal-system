"""
Qdrant writer for the russian_laws_v1 collection.

Pipeline position: embedder → **qdrant_writer**

Each point stores:
  - named dense vector  "dense":  list[float]          (embedding model)
  - named sparse vector "sparse": SparseVector(empty)  (BM25 placeholder for M2)
  - payload with all RussianChunk fields required for retrieval

Collection isolation:
  The hard assertion on COLLECTION_NAME is an explicit safety guard — this
  writer must NEVER write to czech_laws_v2 or any other collection.

Upsert is idempotent:
  chunk_id is already a deterministic UUID5 (set by chunk_builder).
  The same chunk_id always maps to the same Qdrant point ID.
  Re-running ingestion overwrites existing points without data corruption.

Sparse vector slot:
  The sparse vector field is present in the schema but all points are written
  with empty indices/values in Milestone 1. This avoids a schema migration
  when Milestone 2 adds the Russian BM25 encoder.
"""
from __future__ import annotations

import logging
import time

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.modules.russia.ingestion.embedder import EmbeddedRussianChunk

log = logging.getLogger(__name__)

# ── Collection identity ───────────────────────────────────────────────────────
COLLECTION_NAME = "russian_laws_v1"
_DENSE_VECTOR_NAME  = "dense"
_SPARSE_VECTOR_NAME = "sparse"

# Safety guard: this writer must NEVER touch any other collection.
_ALLOWED_COLLECTION = COLLECTION_NAME

# ── Timeouts / retry ─────────────────────────────────────────────────────────
_QDRANT_TIMEOUT = 120  # seconds — large batches need time
_RETRY_BASE_WAIT = 2   # seconds — exponential back-off base


class RussianLawQdrantWriter:
    """
    Writes embedded Russian law chunks to the russian_laws_v1 Qdrant collection.

    Usage:
        writer = RussianLawQdrantWriter(url="http://qdrant:6333")
        writer.ensure_collection(dimension=384)
        writer.upsert_batch(embedded_chunks)
    """

    def __init__(self, url: str, api_key: str | None = None) -> None:
        self._client = QdrantClient(url=url, api_key=api_key, timeout=_QDRANT_TIMEOUT)

    # ── Collection management ─────────────────────────────────────────────────

    def ensure_collection(self, dimension: int) -> None:
        """
        Create russian_laws_v1 with dense + sparse schema if it does not exist.
        Idempotent — safe to call at the start of every ingestion run.

        Args:
            dimension: dense vector size from embedder.dimension (never hardcoded)
        """
        self._assert_target_collection()
        if self._client.collection_exists(COLLECTION_NAME):
            log.info("qdrant_writer.collection_exists name=%r", COLLECTION_NAME)
            return

        self._client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                _DENSE_VECTOR_NAME: models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE,
                ),
            },
            sparse_vectors_config={
                _SPARSE_VECTOR_NAME: models.SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=False),
                ),
            },
        )
        log.info(
            "qdrant_writer.collection_created name=%r dim=%d",
            COLLECTION_NAME, dimension,
        )

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert_batch(self, embedded: list[EmbeddedRussianChunk], retries: int = 3) -> None:
        """
        Upsert a batch of embedded chunks. Idempotent via deterministic chunk_id.

        Args:
            embedded: list of EmbeddedRussianChunk produced by RussianLawEmbedder
            retries: number of retry attempts on transient Qdrant errors
        """
        self._assert_target_collection()
        if not embedded:
            return

        points = [self._to_point(e) for e in embedded]

        for attempt in range(1, retries + 1):
            try:
                self._client.upsert(collection_name=COLLECTION_NAME, points=points)
                log.debug("qdrant_writer.upserted count=%d", len(points))
                return
            except Exception as exc:
                if attempt == retries:
                    raise
                wait = _RETRY_BASE_WAIT ** attempt
                log.warning(
                    "qdrant_writer.upsert_retry attempt=%d/%d wait=%ds err=%s",
                    attempt, retries, wait, exc,
                )
                time.sleep(wait)

    def count(self) -> int:
        """Return exact point count in russian_laws_v1. Returns 0 if collection absent."""
        self._assert_target_collection()
        try:
            result = self._client.count(collection_name=COLLECTION_NAME, exact=True)
            return result.count
        except Exception:
            return 0

    def health_check(self) -> bool:
        """Return True if Qdrant is reachable."""
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False

    def collection_exists(self) -> bool:
        """Return True if russian_laws_v1 exists."""
        return self._client.collection_exists(COLLECTION_NAME)

    def get_dense_vector_size(self) -> int | None:
        """
        Return the dense vector size stored in the collection schema.
        Returns None if collection does not exist or schema cannot be read.
        """
        try:
            info = self._client.get_collection(COLLECTION_NAME)
            vectors = info.config.params.vectors
            if isinstance(vectors, dict):
                dense = vectors.get(_DENSE_VECTOR_NAME)
                if dense is not None:
                    return int(dense.size)
            elif hasattr(vectors, "size"):
                return int(vectors.size)
        except Exception:
            pass
        return None

    def has_sparse_vector_field(self) -> bool:
        """Return True if the sparse vector field exists in the collection schema."""
        try:
            info = self._client.get_collection(COLLECTION_NAME)
            sparse = info.config.params.sparse_vectors
            if sparse is None:
                return False
            if isinstance(sparse, dict):
                return _SPARSE_VECTOR_NAME in sparse
            return hasattr(sparse, _SPARSE_VECTOR_NAME)
        except Exception:
            return False

    # ── Internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _assert_target_collection() -> None:
        """
        Hard guard: raises AssertionError if COLLECTION_NAME has been changed.
        Prevents any accidental writes to czech_laws_v2 or other collections.
        """
        assert COLLECTION_NAME == _ALLOWED_COLLECTION, (
            f"Collection name tampering detected: {COLLECTION_NAME!r} != {_ALLOWED_COLLECTION!r}"
        )

    @staticmethod
    def _to_point(e: EmbeddedRussianChunk) -> models.PointStruct:
        """Build a Qdrant PointStruct with dense + sparse (empty) vectors."""
        assert e.chunk.text.strip(), (
            f"Refusing to write empty-text chunk: fragment_id={e.chunk.fragment_id!r}"
        )
        return models.PointStruct(
            id=e.chunk.chunk_id,  # already a UUID5 string from chunk_builder
            vector={
                _DENSE_VECTOR_NAME: e.vector,
                _SPARSE_VECTOR_NAME: models.SparseVector(
                    indices=e.sparse_indices,
                    values=e.sparse_values,
                ),
            },
            payload=RussianLawQdrantWriter._build_payload(e),
        )

    @staticmethod
    def _build_payload(e: EmbeddedRussianChunk) -> dict:
        c = e.chunk
        return {
            "chunk_id":       c.chunk_id,
            "fragment_id":    c.fragment_id,
            "law_id":         c.law_id,
            "law_title":      c.law_title,
            "law_short":      c.law_short,
            "article_num":    c.article_num,
            "article_heading": c.article_heading,
            "part_num":       c.part_num,
            "razdel":         c.razdel,
            "glava":          c.glava,
            "text":           c.text,
            "chunk_index":    c.chunk_index,
            "source_type":    c.source_type,
            "source_file":    c.source_file,
            "is_tombstone":   c.is_tombstone,
        }
