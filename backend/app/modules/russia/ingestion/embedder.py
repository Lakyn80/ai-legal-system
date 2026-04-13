"""
Embedder for Russian law chunks — Milestone 1 (dense) / Milestone 2 (+ sparse BM25).

Pipeline position: chunk_builder → **embedder** → qdrant_writer

Responsibilities:
- Wrap EmbeddingService with a typed interface for RussianChunk
- Produce EmbeddedRussianChunk: chunk + dense vector + optional sparse vector
- Expose runtime embedding dimension so qdrant_writer never hardcodes it

Milestone 1 scope:
- Dense vectors only (no BM25 / sparse encoding) when bm25_encoder is None
- Sparse fields are left empty — the Qdrant schema slot exists but is not populated

Milestone 2 scope (Step 7):
- Pass a RussianBM25Encoder to populate sparse_indices / sparse_values

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
    A RussianChunk paired with its dense embedding vector and optional BM25 sparse vector.

    sparse_indices / sparse_values are empty when no BM25 encoder is provided.
    """
    chunk: RussianChunk
    vector: list[float]
    sparse_indices: list[int]
    sparse_values: list[float]


class RussianLawEmbedder:
    """
    Embeds RussianChunk objects using dense vectors and (optionally) BM25 sparse vectors.

    Usage:
        # Dense only (Milestone 1):
        embedder = RussianLawEmbedder(embedding_service)

        # Dense + sparse (Milestone 2 / Step 7):
        from app.modules.russia.ingestion.sparse_encoder import RussianBM25Encoder, IDFTable
        idf = IDFTable.load(path)
        encoder = RussianBM25Encoder(idf)
        embedder = RussianLawEmbedder(embedding_service, bm25_encoder=encoder)

        embedded = embedder.embed_batch(chunks)
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        bm25_encoder=None,
    ) -> None:
        self._service = embedding_service
        self._bm25 = bm25_encoder  # RussianBM25Encoder | None

    @property
    def dimension(self) -> int:
        """Runtime embedding dimension — never hardcoded."""
        return self._service.dimension

    def embed_batch(self, chunks: list[RussianChunk]) -> list[EmbeddedRussianChunk]:
        """
        Embed a batch of RussianChunk objects.

        Returns EmbeddedRussianChunk instances in the same order as the input.
        Sparse fields are populated only if a bm25_encoder was provided.

        Args:
            chunks: list of RussianChunk objects with non-empty text

        Returns:
            List of EmbeddedRussianChunk in input order.
        """
        if not chunks:
            return []

        texts = [c.text for c in chunks]
        dense_vectors = self._service.embed_documents(texts)

        log.debug(
            "embedder.batch size=%d dim=%d sparse=%s",
            len(chunks), self.dimension, self._bm25 is not None,
        )

        result = []
        for chunk, dense_vector, text in zip(chunks, dense_vectors, texts, strict=True):
            if self._bm25 is not None:
                sparse_indices, sparse_values = self._bm25.encode(text)
            else:
                sparse_indices, sparse_values = [], []

            result.append(EmbeddedRussianChunk(
                chunk=chunk,
                vector=dense_vector,
                sparse_indices=sparse_indices,
                sparse_values=sparse_values,
            ))

        return result
