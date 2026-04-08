"""
Embedding adapter for Czech law chunks.

Wraps the project's EmbeddingService with a typed interface so that
service.py and cli.py stay decoupled from the embedding implementation.

Batch size is controlled by the caller (CzechLawIngestionService) so
that memory pressure stays predictable during long-running ingestion.
The embedder itself is stateless — it holds only a reference to the
shared EmbeddingService singleton.
"""

from __future__ import annotations

from app.modules.common.embeddings.profile import EmbeddingProfile
from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.czechia.ingestion.schemas import CzechLawChunk, EmbeddedLawChunk


class CzechLawEmbedder:
    def __init__(self, embedding_service: EmbeddingService) -> None:
        self._service = embedding_service

    @property
    def dimension(self) -> int:
        return self._service.dimension

    @property
    def profile(self) -> EmbeddingProfile:
        return self._service.profile

    def embed_batch(self, chunks: list[CzechLawChunk]) -> list[EmbeddedLawChunk]:
        """
        Embed a list of chunks and return EmbeddedLawChunk pairs in the same order.

        The caller is responsible for choosing a batch size that fits in memory.
        For sentence-transformer models a batch of 32–128 is typical.
        For the hash provider any size is safe.
        """
        if not chunks:
            return []
        texts = [c.text for c in chunks]
        vectors = self._service.embed_documents(texts)
        return [
            EmbeddedLawChunk(chunk=chunk, vector=vector)
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
