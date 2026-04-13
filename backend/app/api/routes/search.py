from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Union

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.dependencies import (
    get_czech_law_retrieval_service,
    get_czech_search_answer_service,
    get_retrieval_service,
    get_search_answer_service,
)
from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.relevance.filter import filter_by_score
from app.modules.common.relevance.reranker import rerank
from app.modules.common.orchestration.search_pipeline import SearchAnswerService
from app.modules.common.qdrant.retrieval_service import RetrievalService
from app.modules.common.qdrant.schemas import SearchRequest, SearchResponse
from app.modules.common.responses.schemas import BatchSearchAnswerResponse, SearchAnswerResponse
from app.modules.czechia.retrieval.service import CzechLawRetrievalService


router = APIRouter()


class BatchSearchRequest(BaseModel):
    queries: list[SearchRequest] = Field(default_factory=list)


@router.post("/search", response_model=SearchResponse)
def search_documents(
    request: SearchRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    czech_retrieval: CzechLawRetrievalService = Depends(get_czech_law_retrieval_service),
):
    if request.country == CountryEnum.CZECHIA and (
        request.domain is None or request.domain == DomainEnum.LAW
    ):
        results = czech_retrieval.search(request)
    else:
        results = retrieval_service.search(request)
    results = filter_by_score(results, min_score=0.9)
    results = rerank(request.query, results)
    _sys = {"irrelevant_query", "no_result", "clarification"}
    results = [r for r in results if r.score > 0 or bool(set(getattr(r, "tags", []) or []) & _sys)]
    return SearchResponse(results=results)


def _answer_single(
    request: SearchRequest,
    search_answer_service: SearchAnswerService,
    czech_answer_service: SearchAnswerService,
) -> SearchAnswerResponse:
    if request.country == CountryEnum.CZECHIA and (
        request.domain is None or request.domain == DomainEnum.LAW
    ):
        return czech_answer_service.answer(request)
    return search_answer_service.answer(request)


@router.post("/search/answer")
def answer_search_query(
    request: Union[BatchSearchRequest, SearchRequest],
    search_answer_service: SearchAnswerService = Depends(get_search_answer_service),
    czech_answer_service: SearchAnswerService = Depends(get_czech_search_answer_service),
):
    # ── batch mode ────────────────────────────────────────────────────────────
    if isinstance(request, BatchSearchRequest):
        if not request.queries:
            return BatchSearchAnswerResponse(results=[])

        results: list[SearchAnswerResponse | None] = [None] * len(request.queries)
        with ThreadPoolExecutor(max_workers=min(8, len(request.queries))) as pool:
            futures = {
                pool.submit(
                    _answer_single, q, search_answer_service, czech_answer_service
                ): idx
                for idx, q in enumerate(request.queries)
            }
            for future in as_completed(futures):
                results[futures[future]] = future.result()

        return BatchSearchAnswerResponse(results=results)  # type: ignore[arg-type]

    # ── single mode (unchanged behavior) ─────────────────────────────────────
    return _answer_single(request, search_answer_service, czech_answer_service)
