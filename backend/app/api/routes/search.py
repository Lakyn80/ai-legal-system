from fastapi import APIRouter, Depends

from app.core.dependencies import (
    get_czech_law_retrieval_service,
    get_czech_search_answer_service,
    get_retrieval_service,
    get_search_answer_service,
)
from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.ambiguity.detector import is_paragraph_only
from app.modules.common.relevance.filter import filter_by_score
from app.modules.common.relevance.reranker import rerank
from app.modules.common.orchestration.search_pipeline import SearchAnswerService
from app.modules.common.qdrant.retrieval_service import RetrievalService
from app.modules.common.qdrant.schemas import SearchRequest, SearchResponse, SearchResultItem
from app.modules.common.responses.schemas import SearchAnswerResponse
from app.modules.czechia.retrieval.service import CzechLawRetrievalService


router = APIRouter()


@router.post("/search", response_model=SearchResponse)
def search_documents(
    request: SearchRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    czech_retrieval: CzechLawRetrievalService = Depends(get_czech_law_retrieval_service),
):
    if request.country == CountryEnum.CZECHIA and (
        request.domain is None or request.domain == DomainEnum.LAW
    ) and is_paragraph_only(request.query):
        return SearchResponse(
            results=[
                SearchResultItem(
                    chunk_id="clarification",
                    document_id="",
                    filename="Upřesnění dotazu",
                    country=CountryEnum.CZECHIA,
                    domain=DomainEnum.LAW,
                    jurisdiction_module="czechia",
                    text="Upřesni zákon (např. zákoník práce, občanský zákoník...)",
                    chunk_index=0,
                    source_type="clarification",
                    source=None,
                    case_id=None,
                    tags=[],
                    score=1.0,
                )
            ]
        )

    if request.country == CountryEnum.CZECHIA and (
        request.domain is None or request.domain == DomainEnum.LAW
    ):
        results = czech_retrieval.search(request)
    else:
        results = retrieval_service.search(request)
    results = filter_by_score(results, min_score=0.9)
    results = rerank(request.query, results)
    results = [result for result in results if result.score > 0]
    return SearchResponse(results=results)


@router.post("/search/answer", response_model=SearchAnswerResponse)
def answer_search_query(
    request: SearchRequest,
    search_answer_service: SearchAnswerService = Depends(get_search_answer_service),
    czech_answer_service: SearchAnswerService = Depends(get_czech_search_answer_service),
):
    if request.country == CountryEnum.CZECHIA and (
        request.domain is None or request.domain == DomainEnum.LAW
    ):
        return czech_answer_service.answer(request)
    return search_answer_service.answer(request)
