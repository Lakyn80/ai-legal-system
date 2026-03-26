from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import CountryEnum, DocumentStatusEnum, DomainEnum


class DocumentRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    filename: str
    path: str
    country: CountryEnum
    domain: DomainEnum
    document_type: str
    source: str | None = None
    uploaded_at: datetime
    case_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: DocumentStatusEnum = DocumentStatusEnum.UPLOADED
    size_bytes: int = 0
    chunk_count: int = 0
    ingested_at: datetime | None = None
    error_message: str | None = None


class DocumentUploadResponse(BaseModel):
    document: DocumentRecord


class DocumentListResponse(BaseModel):
    documents: list[DocumentRecord]


class DocumentIngestionResult(BaseModel):
    document_id: str
    filename: str
    status: str
    chunk_count: int = 0
    error: str | None = None


class IngestRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    results: list[DocumentIngestionResult]
