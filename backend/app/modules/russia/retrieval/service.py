"""
Russian law retrieval service — Milestone 1.

Step 5: exact article lookup (no vector search)
Step 6: dense semantic search added

Topic retrieval, BM25 query-time, ambiguity handling, and LLM integration
are out of scope for this step.

Does NOT:
  - Implement BM25 query-time retrieval
  - Perform query expansion
  - Call any LLM
  - Import ingestion modules
"""
from __future__ import annotations

from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.russia.retrieval.dense_retriever import RussianDenseRetriever
from app.modules.russia.retrieval.exact_lookup import RussianExactLookup
from app.modules.russia.retrieval.schemas import ArticleLookupResult, RussianSearchResult


class RussianRetrievalService:
    """
    Retrieval service for Russian law — Milestone 1.

    Supports:
      - Exact article lookup (no embedding, pure payload filter)
      - Dense semantic search (embedding + vector search)

    Usage:
        service = RussianRetrievalService(
            embedding_service=...,
            qdrant_url="http://qdrant:6333",
        )
        result = service.get_article("local:ru/tk", "81")
        hits   = service.search("расторжение договора", law_id="local:ru/tk")
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        qdrant_url: str,
        qdrant_api_key: str | None = None,
    ) -> None:
        self._exact = RussianExactLookup(url=qdrant_url, api_key=qdrant_api_key)
        self._dense = RussianDenseRetriever(
            embedding_service=embedding_service,
            url=qdrant_url,
            api_key=qdrant_api_key,
        )

    def get_article(
        self,
        law_id: str,
        article_num: str,
        part_num: int | None = None,
    ) -> ArticleLookupResult:
        """
        Look up a Russian law article by law_id + article_num.

        Args:
            law_id:      Canonical IRI, e.g. 'local:ru/tk'
            article_num: Article number as string, e.g. '81', '19.1'
            part_num:    Optional — return only the specified part

        Returns:
            ArticleLookupResult. Always structured — never raises.
        """
        return self._exact.get_article(law_id=law_id, article_num=article_num, part_num=part_num)

    def search(
        self,
        query: str,
        law_id: str | None = None,
        top_k: int = 10,
    ) -> list[RussianSearchResult]:
        """
        Dense semantic search over russian_laws_v1.

        Args:
            query:   Free-text query
            law_id:  Optional — restrict to one law (e.g. 'local:ru/tk')
            top_k:   Maximum results to return

        Returns:
            List of RussianSearchResult in score-descending order.
        """
        return self._dense.search(query=query, law_id=law_id, top_k=top_k)
