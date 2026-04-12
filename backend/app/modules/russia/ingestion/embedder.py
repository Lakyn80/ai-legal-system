"""
Embedder for Russian law chunks — Milestone 1 (dense only).

Pipeline position: chunk_builder → **embedder** → qdrant_writer

Responsibilities:
- Wrap EmbeddingService with a typed interface for RussianChunk
- Produce EmbeddedRussianChunk: chunk + dense vector
- Expose runtime embedding dimension so qdrant_writer never hardcodes it

Milestone 1 scope:
- Dense vectors only (no BM25 / sparse encoding)
- Sparse fields are left empty — the Qdrant schema slot exists but is not populated
  until Milestone 2 adds a Russian BM25 encoder

Does NOT:
- Write to Qdrant
- Perform any retrieval
- Import any retrieval modules
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.russia.ingestion.schemas import RussianChunk

log = logging.getLogger(__name__)


@dataclass
class EmbeddedRussianChunk:
    """
    A RussianChunk paired with its dense embedding vector.

    sparse_indices / sparse_values are always empty in Milestone 1.
    The Qdrant writer stores them as an empty SparseVector so the collection
    schema is already correct when Milestone 2 adds BM25.
    """
    chunk: RussianChunk
    vector: list[float]
    sparse_indices: list[int]
    sparse_values: list[float]


class RussianLawEmbedder:
    """
    Embeds RussianChunk objects using the project's EmbeddingService.

    Usage:
        embedder = RussianLawEmbedder(embedding_service)
        embedded = embedder.embed_batch(chunks)
    """

    def __init__(self, embedding_service: EmbeddingService) -> None:
        self._service = embedding_service

    @property
    def dimension(self) -> int:
        """Runtime embedding dimension — never hardcoded."""
        return self._service.dimension

    def embed_batch(self, chunks: list[RussianChunk]) -> list[EmbeddedRussianChunk]:
        """
        Embed a batch of RussianChunk objects.

        Returns EmbeddedRussianChunk instances in the same order as the input.
        Sparse fields are empty (Milestone 1 — dense only).

        Args:
            chunks: list of RussianChunk objects with non-empty text

        Returns:
            List of EmbeddedRussianChunk in input order.
        """
        if not chunks:
            return []

        texts = [c.text for c in chunks]
        dense_vectors = self._service.embed_documents(texts)

        log.debug("embedder.batch size=%d dim=%d", len(chunks), self.dimension)

        return [
            EmbeddedRussianChunk(
                chunk=chunk,
                vector=dense_vector,
                sparse_indices=[],
                sparse_values=[],
            )
            for chunk, dense_vector in zip(chunks, dense_vectors, strict=True)
        ]
