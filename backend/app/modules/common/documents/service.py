from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.enums import CountryEnum, DomainEnum
from app.core.exceptions import DocumentUploadError
from app.modules.common.documents.repository import FileDocumentRepository
from app.modules.common.documents.schemas import DocumentRecord
from app.modules.common.storage.file_storage import FileStorageService


class DocumentService:
    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".json", ".zip"}

    def __init__(
        self,
        storage_service: FileStorageService,
        document_repository: FileDocumentRepository,
    ) -> None:
        self.storage_service = storage_service
        self.document_repository = document_repository

    async def upload_document(
        self,
        upload_file: UploadFile,
        country: CountryEnum,
        domain: DomainEnum,
        document_type: str,
        source: str | None,
        case_id: str | None,
        tags: list[str],
    ) -> DocumentRecord:
        content = await upload_file.read()
        if not content:
            raise DocumentUploadError("Uploaded file is empty.")

        filename = upload_file.filename or "document.bin"
        return self._create_document_record(
            filename=filename,
            content=content,
            country=country,
            domain=domain,
            document_type=document_type,
            source=source,
            case_id=case_id,
            tags=tags,
        )

    def import_local_document(
        self,
        file_path: Path,
        country: CountryEnum,
        domain: DomainEnum,
        document_type: str,
        source: str | None,
        case_id: str | None,
        tags: list[str],
    ) -> DocumentRecord:
        if not file_path.exists() or not file_path.is_file():
            raise DocumentUploadError(f"File not found: {file_path}")

        content = file_path.read_bytes()
        if not content:
            raise DocumentUploadError("Imported file is empty.")

        return self._create_document_record(
            filename=file_path.name,
            content=content,
            country=country,
            domain=domain,
            document_type=document_type,
            source=source,
            case_id=case_id,
            tags=tags,
        )

    def _create_document_record(
        self,
        filename: str,
        content: bytes,
        country: CountryEnum,
        domain: DomainEnum,
        document_type: str,
        source: str | None,
        case_id: str | None,
        tags: list[str],
    ) -> DocumentRecord:
        extension = Path(filename).suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise DocumentUploadError("Unsupported file type. Allowed extensions: PDF, DOCX, TXT, JSON, ZIP.")

        document_id = str(uuid4())
        path = self.storage_service.save_file(document_id, filename, content)

        record = DocumentRecord(
            id=document_id,
            filename=filename,
            path=path,
            country=country,
            domain=domain,
            document_type=document_type,
            source=source,
            uploaded_at=datetime.now(timezone.utc),
            case_id=case_id,
            tags=tags,
            size_bytes=len(content),
        )
        return self.document_repository.save(record)

    def list_documents(self) -> list[DocumentRecord]:
        return self.document_repository.list()
