"""
Russian law retrieval service — Milestone 1 (exact lookup only).

This is intentionally minimal. It wraps RussianExactLookup and provides a
single unified entry point for retrieval. Dense search and topic retrieval
are added in later steps.

Does NOT:
  - Perform vector / semantic search
  - Call the embedding service
  - Implement BM25 query-time retrieval
  - Import ingestion modules
"""
from __future__ import annotations

from app.modules.russia.retrieval.exact_lookup import RussianExactLookup
from app.modules.russia.retrieval.schemas import ArticleLookupResult


class RussianRetrievalService:
    """
    Retrieval service for Russian law — Milestone 1.

    Currently supports only exact article lookup. Dense/topic search
    will be added in subsequent milestones.

    Usage:
        service = RussianRetrievalService(qdrant_url="http://qdrant:6333")
        result = service.get_article("local:ru/tk", "81")
    """

    def __init__(self, qdrant_url: str, qdrant_api_key: str | None = None) -> None:
        self._exact = RussianExactLookup(url=qdrant_url, api_key=qdrant_api_key)

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
            ArticleLookupResult. Always returns a structured result —
            never raises on missing articles (hit=False is returned instead).
        """
        return self._exact.get_article(law_id=law_id, article_num=article_num, part_num=part_num)
