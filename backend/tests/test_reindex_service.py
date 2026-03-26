from pathlib import Path

from app.core.enums import CountryEnum, DomainEnum
from app.modules.common.documents.schemas import DocumentRecord
from app.modules.common.embeddings.profile import EmbeddingProfile
from app.modules.common.qdrant.reindex_service import CollectionReindexService


class FakeRepository:
    def __init__(self, records: list[DocumentRecord]) -> None:
        self.records = records
        self.saved: list[DocumentRecord] = []

    def list(self) -> list[DocumentRecord]:
        return self.records

    def save(self, record: DocumentRecord) -> DocumentRecord:
        self.saved.append(record)
        return record


class FakeIngestionService:
    def build_embedded_chunks(self, record: DocumentRecord):
        return (["chunk-a", "chunk-b"], 2)


class FakeEmbeddingService:
    profile = EmbeddingProfile(
        provider="hash",
        model="deterministic-hash-384",
        dimension=384,
        revision="deterministic_hash_v2",
    )


class FakeVectorStore:
    alias_name = "legal_documents_active"

    def __init__(self) -> None:
        self.upserts: list[tuple[str, int]] = []
        self.switched_to: str | None = None
        self.deleted: str | None = None

    def get_active_collection_name(self) -> str | None:
        return "legal_documents__hash__old__v1"

    def create_next_collection_for_profile(self, profile: EmbeddingProfile) -> str:
        return "legal_documents__hash__new__v2"

    def upsert_chunks(self, chunks, vector_size: int, collection_name: str | None = None) -> None:
        self.upserts.append((collection_name or "", vector_size))

    def switch_alias(self, target_collection: str) -> None:
        self.switched_to = target_collection

    def delete_collection(self, collection_name: str) -> None:
        self.deleted = collection_name


def build_record(document_id: str) -> DocumentRecord:
    return DocumentRecord(
        id=document_id,
        filename="collection.json",
        path=str(Path(f"/tmp/{document_id}.json")),
        country=CountryEnum.CZECHIA,
        domain=DomainEnum.LAW,
        document_type="legal_collection_json",
        source="test",
        uploaded_at="2026-03-21T00:00:00Z",
        tags=["law"],
    )


def test_reindex_service_creates_new_collection_and_switches_alias():
    repository = FakeRepository([build_record("doc-1"), build_record("doc-2")])
    vector_store = FakeVectorStore()
    service = CollectionReindexService(
        document_repository=repository,
        ingestion_service=FakeIngestionService(),
        embedding_service=FakeEmbeddingService(),
        vector_store=vector_store,
    )

    result = service.reindex(delete_previous_collection=True)

    assert result.status == "completed"
    assert result.documents_total == 2
    assert result.documents_reindexed == 2
    assert vector_store.switched_to == "legal_documents__hash__new__v2"
    assert vector_store.deleted == "legal_documents__hash__old__v1"
    assert len(vector_store.upserts) == 2
