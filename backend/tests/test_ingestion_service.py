from pathlib import Path

from app.core.enums import CountryEnum, DocumentStatusEnum, DomainEnum
from app.modules.common.embeddings.profile import EmbeddingProfile
from app.modules.common.documents.ingestion_service import DocumentIngestionService
from app.modules.common.documents.schemas import DocumentRecord


class FakeRepository:
    def __init__(self, record: DocumentRecord) -> None:
        self.record = record
        self.saved: list[DocumentRecord] = []

    def get(self, document_id: str) -> DocumentRecord | None:
        return self.record if self.record.id == document_id else None

    def list(self) -> list[DocumentRecord]:
        return [self.record]

    def save(self, record: DocumentRecord) -> DocumentRecord:
        self.record = record
        self.saved.append(record)
        return record


class FakeParser:
    def parse(self, record: DocumentRecord) -> str:
        return "First chunk. Second chunk."


class FakeChunker:
    def chunk_text(self, text: str) -> list[str]:
        return ["First chunk", "Second chunk"]


class FakeEmbeddings:
    dimension = 3
    profile = EmbeddingProfile(
        provider="hash",
        model="deterministic-hash-3",
        dimension=3,
        revision="deterministic_hash_v2",
    )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeVectorStore:
    def __init__(self) -> None:
        self.upserts = []
        self.profile_ensured = None

    def ensure_active_collection(self, profile) -> None:
        self.profile_ensured = profile

    def upsert_chunks(self, chunks, vector_size: int) -> None:
        self.upserts.append((chunks, vector_size))


def test_ingest_record_updates_status_and_pushes_chunks():
    record = DocumentRecord(
        id="doc-1",
        filename="collection.json",
        path=str(Path("/tmp/collection.json")),
        country=CountryEnum.CZECHIA,
        domain=DomainEnum.LAW,
        document_type="legal_collection_json",
        source="test",
        uploaded_at="2026-03-21T00:00:00Z",
        tags=["law"],
    )
    repository = FakeRepository(record)
    vector_store = FakeVectorStore()
    service = DocumentIngestionService(
        document_repository=repository,
        parser_service=FakeParser(),
        chunking_service=FakeChunker(),
        embedding_service=FakeEmbeddings(),
        vector_store=vector_store,
    )

    result = service.ingest_record(record)

    assert result.status == DocumentStatusEnum.INGESTED.value
    assert result.chunk_count == 2
    assert repository.record.status == DocumentStatusEnum.INGESTED
    assert vector_store.upserts
    assert vector_store.profile_ensured == FakeEmbeddings.profile
