from pathlib import Path

from app.core.exceptions import DocumentProcessingError
from app.modules.common.documents.schemas import DocumentRecord
from app.modules.common.parsing.legal_collection import LegalCollectionParser

try:
    from pypdf import PdfReader
except ModuleNotFoundError:
    PdfReader = None

try:
    from docx import Document as DocxDocument
except ModuleNotFoundError:
    DocxDocument = None


class DocumentParserService:
    def __init__(self, legal_collection_parser: LegalCollectionParser | None = None) -> None:
        self.legal_collection_parser = legal_collection_parser or LegalCollectionParser()

    def parse(self, record: DocumentRecord) -> str:
        path = Path(record.path)
        suffix = path.suffix.lower()
        if suffix == ".txt":
            return path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".json":
            return self.legal_collection_parser.parse_json_file(path)
        if suffix == ".zip":
            return self.legal_collection_parser.parse_zip_file(path)
        if suffix == ".pdf":
            return self._parse_pdf(path)
        if suffix == ".docx":
            return self._parse_docx(path)
        raise DocumentProcessingError(f"Unsupported file type: {suffix}")

    @staticmethod
    def _parse_pdf(path: Path) -> str:
        if PdfReader is None:
            raise DocumentProcessingError("PDF parsing requires pypdf to be installed.")
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()

    @staticmethod
    def _parse_docx(path: Path) -> str:
        if DocxDocument is None:
            raise DocumentProcessingError("DOCX parsing requires python-docx to be installed.")
        document = DocxDocument(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
