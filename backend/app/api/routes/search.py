from fastapi import APIRouter, Depends

from app.core.dependencies import get_retrieval_service, get_search_answer_service
from app.modules.common.orchestration.search_pipeline import SearchAnswerService
from app.modules.common.qdrant.retrieval_service import RetrievalService
from app.modules.common.qdrant.schemas import SearchRequest, SearchResponse
from app.modules.common.responses.schemas import SearchAnswerResponse


router = APIRouter()


@router.post("/search", response_model=SearchResponse)
def search_documents(
    request: SearchRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
):
    results = retrieval_service.search(request)
    return SearchResponse(results=results)


@router.post("/search/answer", response_model=SearchAnswerResponse)
def answer_search_query(
    request: SearchRequest,
    search_answer_service: SearchAnswerService = Depends(get_search_answer_service),
):
    return search_answer_service.answer(request)
