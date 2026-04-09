from __future__ import annotations

from app.modules.common.qdrant.schemas import HybridSearchResponse
from app.modules.czechia.retrieval.service import CzechLawRetrievalService


class CzechLawRetrievalAdapter:
    """
    Wraps CzechLawRetrievalService so it can be used as a drop-in replacement
    for the retrieval_service slot in SearchAnswerService.

    SearchAnswerService calls:
      - retrieve(request) -> HybridSearchResponse   (answer pipeline)
      - search(request)   -> list[SearchResultItem] (used internally by some paths)
    """

    def __init__(self, service: CzechLawRetrievalService) -> None:
        self.service = service

    def search(self, request):
        return self.service.search(request)

    def retrieve(self, request) -> HybridSearchResponse:
        results = self.service.search(request)
        return HybridSearchResponse(results=results)
