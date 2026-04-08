"""
Qdrant writer for the czech_laws collection.

Uses qdrant_client directly (not the shared QdrantVectorStore) so that the
payload schema can be richer than ChunkPayload without modifying shared code.

Collection: czech_laws  (separate from legal_documents — no collision risk)

The payload stored per point includes all relation hook fields so that future
graph-aware retrieval can attach law metadata, outgoing links, term references,
and definition references without requiring a schema migration or re-ingestion.

Upsert is idempotent:
  chunk_id → deterministic uuid5 → Qdrant point ID
  Re-running ingestion overwrites existing points with identical data.

Phase 2 extension:
  - Add a search() method here (or a companion CzechLawRetrievalService)
    that queries czech_laws and enriches results with relation index data.
  - The payload fields outgoing_link_ids / incoming_link_ids / term_refs
    can be populated by a graph-enrichment pass that reads the links section
    and updates existing Qdrant points via set_payload().
"""

from __future__ import annotations

import time
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.modules.czechia.ingestion.schemas import EmbeddedLawChunk

COLLECTION_NAME = "czech_laws"

# Qdrant HTTP timeout in seconds — large batches on a loaded instance need more time.
_QDRANT_TIMEOUT = 120


class CzechLawQdrantWriter:
    def __init__(self, url: str, api_key: str | None = None) -> None:
        self._client = QdrantClient(url=url, api_key=api_key, timeout=_QDRANT_TIMEOUT)

    def ensure_collection(self, dimension: int) -> None:
        """
        Create the czech_laws collection if it does not exist.
        Idempotent — safe to call at the start of every ingestion run.
        """
        if self._client.collection_exists(COLLECTION_NAME):
            return
        self._client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=dimension,
                distance=models.Distance.COSINE,
            ),
        )

    def is_law_ingested(self, law_iri: str) -> bool:
        """
        Return True if at least one point with the given law_iri already exists
        in the collection.  Used to skip ZIPs that were ingested in a previous run.

        Fast: uses Qdrant count() with a payload filter — no vectors fetched.
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
                exact=False,  # approximate count is sufficient for skip detection
            )
            return result.count > 0
        except Exception:
            return False

    def upsert_batch(self, embedded: list[EmbeddedLawChunk], retries: int = 3) -> None:
        """
        Upsert a batch of embedded chunks.  Idempotent via deterministic chunk_id.
        Retries up to `retries` times on timeout with exponential backoff.
        """
        if not embedded:
            return
        points = [
            models.PointStruct(
                id=self._point_id(e.chunk.chunk_id),
                vector=e.vector,
                payload=self._build_payload(e),
            )
            for e in embedded
        ]
        for attempt in range(1, retries + 1):
            try:
                self._client.upsert(collection_name=COLLECTION_NAME, points=points)
                return
            except Exception as exc:
                if attempt == retries:
                    raise
                wait = 2 ** attempt
                print(f"\n  [qdrant_writer] upsert timeout (attempt {attempt}/{retries}), retrying in {wait}s... ({exc})")
                time.sleep(wait)

    def health_check(self) -> bool:
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        """Convert chunk_id to a UUID string compatible with Qdrant point IDs."""
        return str(uuid5(NAMESPACE_URL, chunk_id))

    @staticmethod
    def _build_payload(e: EmbeddedLawChunk) -> dict:
        """
        Build the Qdrant point payload.

        All relation hook fields are included even when empty so that
        phase 2 can update them via set_payload() without schema changes.
        """
        c = e.chunk
        return {
            # Core retrieval fields
            "chunk_id": c.chunk_id,
            "fragment_id": c.fragment_id,
            "law_iri": c.law_iri,
            "text": c.text,
            "chunk_index": c.chunk_index,
            "source_type": c.source_type,
            # Phase 1 relation hooks
            "metadata_ref": c.metadata_ref,
            "definition_refs": c.definition_refs,
            # Phase 2 relation hooks (empty in phase 1)
            "outgoing_link_ids": c.outgoing_link_ids,
            "incoming_link_ids": c.incoming_link_ids,
            "term_refs": c.term_refs,
            "relation_keys": c.relation_keys,
        }
