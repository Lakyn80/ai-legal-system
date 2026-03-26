from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.dependencies import get_document_service, get_ingestion_service
from app.core.enums import CountryEnum, DomainEnum
from app.core.exceptions import ApplicationError
from app.modules.common.documents.ingestion_service import DocumentIngestionService
from app.modules.common.documents.schemas import (
    DocumentListResponse,
    DocumentUploadResponse,
    IngestRequest,
    IngestResponse,
)
from app.modules.common.documents.service import DocumentService


router = APIRouter()


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    country: CountryEnum = Form(...),
    domain: DomainEnum = Form(...),
    document_type: str = Form(...),
    source: str | None = Form(default=None),
    case_id: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    document_service: DocumentService = Depends(get_document_service),
):
    parsed_tags = [item.strip() for item in (tags or "").split(",") if item.strip()]
    try:
        record = await document_service.upload_document(
            upload_file=file,
            country=country,
            domain=domain,
            document_type=document_type,
            source=source,
            case_id=case_id,
            tags=parsed_tags,
        )
    except ApplicationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DocumentUploadResponse(document=record)


@router.post("/ingest", response_model=IngestResponse)
def ingest_documents(
    request: IngestRequest,
    ingestion_service: DocumentIngestionService = Depends(get_ingestion_service),
):
    results = ingestion_service.ingest_documents(request.document_ids)
    return IngestResponse(results=results)


@router.get("", response_model=DocumentListResponse)
def list_documents(
    document_service: DocumentService = Depends(get_document_service),
):
    return DocumentListResponse(documents=document_service.list_documents())
