"""
Dense vector search against russian_laws_v1.

Retrieval strategy:
  1. Embed query text via the project EmbeddingService
  2. Call Qdrant query_points on the "dense" named vector
  3. Optionally filter by law_id payload field
  4. Return RussianSearchResult list in score-descending order (Qdrant default)

Does NOT:
  - Perform BM25 / sparse retrieval
  - Expand the query
  - Rerank results
  - Call any LLM
  - Import ingestion modules
"""
from __future__ import annotations

import logging

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.russia.retrieval.schemas import RussianSearchResult

log = logging.getLogger(__name__)

COLLECTION_NAME = "russian_laws_v1"
_DENSE_VECTOR_NAME = "dense"
_QDRANT_TIMEOUT = 30


class RussianDenseRetriever:
    """
    Semantic dense search against russian_laws_v1.

    Usage:
        retriever = RussianDenseRetriever(embedding_service, url="http://qdrant:6333")
        results = retriever.search("расторжение трудового договора", law_id="local:ru/tk", top_k=10)
    """

    def __init__(self, embedding_service: EmbeddingService, url: str, api_key: str | None = None) -> None:
        self._embedding = embedding_service
        self._client = QdrantClient(url=url, api_key=api_key, timeout=_QDRANT_TIMEOUT)

    def search(
        self,
        query: str,
        law_id: str | None = None,
        top_k: int = 10,
    ) -> list[RussianSearchResult]:
        """
        Embed `query` and search russian_laws_v1 for the most similar chunks.

        Args:
            query:   Free-text query in Russian (or any language the embedding model handles)
            law_id:  Optional canonical IRI to restrict results to one law
                     (e.g. 'local:ru/tk'). None = search all ingested laws.
            top_k:   Maximum number of results to return.

        Returns:
            List of RussianSearchResult in score-descending order.
            Empty list on error or if collection is empty.
        """
        if not query.strip() or top_k <= 0:
            return []

        query_vector = self._embedding.embed_query(query)

        query_filter = _build_law_filter(law_id)

        try:
            response = self._client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                using=_DENSE_VECTOR_NAME,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            log.error("dense_retriever.search_failed query=%r err=%s", query[:60], exc)
            return []

        results = [_point_to_result(p) for p in response.points]

        log.debug(
            "dense_retriever.search query=%r law_id=%r top_k=%d results=%d",
            query[:60], law_id, top_k, len(results),
        )
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
