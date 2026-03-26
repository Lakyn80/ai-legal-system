import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from starlette.datastructures import UploadFile

from app.core.enums import CountryEnum, DomainEnum
from app.core.exceptions import DocumentUploadError
from app.modules.common.documents.repository import FileDocumentRepository
from app.modules.common.documents.service import DocumentService
from app.modules.common.storage.file_storage import FileStorageService


def build_service(tmp_path: Path) -> DocumentService:
    storage = FileStorageService(tmp_path / "storage")
    repository = FileDocumentRepository(storage)
    return DocumentService(storage_service=storage, document_repository=repository)


def test_upload_document_accepts_zip_file(tmp_path: Path):
    service = build_service(tmp_path)
    upload = UploadFile(file=BytesIO(b"fake zip"), filename="collection.zip")

    record = asyncio.run(
        service.upload_document(
            upload_file=upload,
            country=CountryEnum.CZECHIA,
            domain=DomainEnum.LAW,
            document_type="legal_collection",
            source="local-test",
            case_id=None,
            tags=["sbirka"],
        )
    )

    assert record.filename == "collection.zip"
    assert Path(record.path).exists()


def test_import_local_document_accepts_json_file(tmp_path: Path):
    service = build_service(tmp_path)
    source = tmp_path / "collection.json"
    source.write_text('{"metadata": {}, "fragmenty": []}', encoding="utf-8")

    record = service.import_local_document(
        file_path=source,
        country=CountryEnum.CZECHIA,
        domain=DomainEnum.LAW,
        document_type="legal_collection_json",
        source="local-test",
        case_id=None,
        tags=["json"],
    )

    assert record.filename == "collection.json"
    assert Path(record.path).exists()


def test_upload_document_rejects_unsupported_extension(tmp_path: Path):
    service = build_service(tmp_path)
    upload = UploadFile(file=BytesIO(b"bad"), filename="collection.exe")

    with pytest.raises(DocumentUploadError):
        asyncio.run(
            service.upload_document(
                upload_file=upload,
                country=CountryEnum.CZECHIA,
                domain=DomainEnum.LAW,
                document_type="bad",
                source=None,
                case_id=None,
                tags=[],
            )
        )
