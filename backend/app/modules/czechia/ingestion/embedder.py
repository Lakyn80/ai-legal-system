"""
Embedding adapter for Czech law chunks.

Wraps the project's EmbeddingService with a typed interface so that
service.py and cli.py stay decoupled from the embedding implementation.

Optionally accepts a CzechBM25Encoder to populate sparse_indices /
sparse_values on each EmbeddedLawChunk.  When no encoder is provided
the sparse fields are left empty — the Qdrant writer handles both cases.

Batch size is controlled by the caller so that memory pressure stays
predictable during long-running ingestion.
"""

from __future__ import annotations

from app.modules.common.embeddings.profile import EmbeddingProfile
from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.czechia.ingestion.schemas import CzechLawChunk, EmbeddedLawChunk

# TYPE_CHECKING import to avoid circular dependency at runtime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.modules.czechia.ingestion.sparse_encoder import CzechBM25Encoder


class CzechLawEmbedder:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        bm25_encoder: CzechBM25Encoder | None = None,
    ) -> None:
        self._service = embedding_service
        self._bm25 = bm25_encoder

    @property
    def dimension(self) -> int:
        return self._service.dimension

    @property
    def profile(self) -> EmbeddingProfile:
        return self._service.profile

    @property
    def has_sparse(self) -> bool:
        """True when BM25 encoder is configured — sparse vectors will be populated."""
        return self._bm25 is not None

    def embed_batch(self, chunks: list[CzechLawChunk]) -> list[EmbeddedLawChunk]:
        """
        Embed a list of chunks and return EmbeddedLawChunk pairs in the same order.

        When a BM25 encoder is configured each chunk also gets sparse_indices /
        sparse_values populated from the BM25 encoding of its text.

        The caller is responsible for choosing a batch size that fits in memory.
        For sentence-transformer models a batch of 32–128 is typical.
        For the hash provider any size is safe.
        """
        if not chunks:
            return []

        texts = [c.text for c in chunks]
        dense_vectors = self._service.embed_documents(texts)

        result: list[EmbeddedLawChunk] = []
        for chunk, dense_vector in zip(chunks, dense_vectors, strict=True):
            if self._bm25 is not None:
                sparse_indices, sparse_values = self._bm25.encode(chunk.text)
            else:
                sparse_indices, sparse_values = [], []

            result.append(EmbeddedLawChunk(
                chunk=chunk,
                vector=dense_vector,
                sparse_indices=sparse_indices,
                sparse_values=sparse_values,
            ))
        return result
