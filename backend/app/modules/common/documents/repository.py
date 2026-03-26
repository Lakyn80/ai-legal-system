from pathlib import Path

from app.modules.common.documents.schemas import DocumentRecord
from app.modules.common.storage.file_storage import FileStorageService


class FileDocumentRepository:
    def __init__(self, storage_service: FileStorageService) -> None:
        self.storage_service = storage_service

    def save(self, record: DocumentRecord) -> DocumentRecord:
        target = self.storage_service.metadata_path(record.id)
        target.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return record

    def get(self, document_id: str) -> DocumentRecord | None:
        target = self.storage_service.metadata_path(document_id)
        if not target.exists():
            return None
        return DocumentRecord.model_validate_json(target.read_text(encoding="utf-8"))

    def list(self) -> list[DocumentRecord]:
        records: list[DocumentRecord] = []
        metadata_dir: Path = self.storage_service.metadata_dir
        for path in metadata_dir.glob("*.json"):
            records.append(DocumentRecord.model_validate_json(path.read_text(encoding="utf-8")))
        return sorted(records, key=lambda item: item.uploaded_at, reverse=True)
