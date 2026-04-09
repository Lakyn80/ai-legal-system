"""
Qdrant writer for the czech_laws_v2 hybrid collection.

Each point stores:
  - named dense vector  "dense":  list[float]            (embedding model)
  - named sparse vector "sparse": SparseVector(BM25)     (from CzechBM25Encoder)
  - rich payload for Czech retrieval pipeline

Sparse vector is optional — when EmbeddedLawChunk.sparse_indices is empty
(e.g. during development with hash provider and no IDFTable) the point is
stored with an empty sparse vector.  This is valid in Qdrant and allows the
collection to exist before a full BM25-enabled re-ingestion.

Upsert is idempotent:
  chunk_id → deterministic uuid5 → Qdrant point ID.
  Re-running ingestion overwrites existing points.
"""

from __future__ import annotations

import time
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.modules.czechia.ingestion.schemas import EmbeddedLawChunk

COLLECTION_NAME = "czech_laws_v2"
_DENSE_VECTOR_NAME  = "dense"
_SPARSE_VECTOR_NAME = "sparse"

# Qdrant HTTP timeout — large batches on a loaded instance need more time.
_QDRANT_TIMEOUT = 120


class CzechLawQdrantWriter:
    def __init__(self, url: str, api_key: str | None = None) -> None:
        self._client = QdrantClient(url=url, api_key=api_key, timeout=_QDRANT_TIMEOUT)

    # ── collection management ──────────────────────────────────────────────────

    def ensure_collection(self, dimension: int) -> None:
        """
        Create czech_laws_v2 with hybrid dense+sparse config if it does not exist.
        Idempotent — safe to call at the start of every ingestion run.
        """
        if self._client.collection_exists(COLLECTION_NAME):
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

    def is_law_ingested(self, law_iri: str) -> bool:
        """
        Return True if at least one point with the given law_iri already exists.
        Uses approximate count — no vectors fetched.
        Returns False if the collection does not yet exist.
        """
        try:
            result = self._client.count(
                collection_name=COLLECTION_NAME,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="law_iri",
                            match=models.MatchValue(value=law_iri),
                        )
                    ]
                ),
                exact=False,
            )
            return result.count > 0
        except Exception:
            return False

    # ── write ──────────────────────────────────────────────────────────────────

    def upsert_batch(self, embedded: list[EmbeddedLawChunk], retries: int = 3) -> None:
        """
        Upsert a batch of embedded chunks with dense + sparse vectors.
        Idempotent via deterministic chunk_id → uuid5 point ID.
        Retries up to `retries` times on timeout with exponential backoff.
        """
        if not embedded:
            return

        points = [self._to_point(e) for e in embedded]

        for attempt in range(1, retries + 1):
            try:
                self._client.upsert(collection_name=COLLECTION_NAME, points=points)
                return
            except Exception as exc:
                if attempt == retries:
                    raise
                wait = 2 ** attempt
                print(
                    f"\n  [qdrant_writer_v2] upsert timeout "
                    f"(attempt {attempt}/{retries}), retrying in {wait}s... ({exc})"
                )
                time.sleep(wait)

    def health_check(self) -> bool:
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False

    # ── internals ──────────────────────────────────────────────────────────────

    @staticmethod
    def _to_point(e: EmbeddedLawChunk) -> models.PointStruct:
        """Build a Qdrant PointStruct with dense + sparse vectors."""
        return models.PointStruct(
            id=str(uuid5(NAMESPACE_URL, e.chunk.chunk_id)),
            vector={
                _DENSE_VECTOR_NAME: e.vector,
                _SPARSE_VECTOR_NAME: models.SparseVector(
                    indices=e.sparse_indices,
                    values=e.sparse_values,
                ),
            },
            payload=CzechLawQdrantWriter._build_payload(e),
        )

    @staticmethod
    def _build_payload(e: EmbeddedLawChunk) -> dict:
        c = e.chunk
        return {
            # Core retrieval fields
            "chunk_id":    c.chunk_id,
            "fragment_id": c.fragment_id,
            "law_iri":     c.law_iri,
            "paragraph":   c.paragraph,
            "text":        c.text,
            "chunk_index": c.chunk_index,
            "source_type": c.source_type,
            # Phase 1 relation hooks
            "metadata_ref":    c.metadata_ref,
            "definition_refs": c.definition_refs,
            # Phase 2 relation hooks (empty in phase 1)
            "outgoing_link_ids": c.outgoing_link_ids,
            "incoming_link_ids": c.incoming_link_ids,
            "term_refs":         c.term_refs,
            "relation_keys":     c.relation_keys,
        }
