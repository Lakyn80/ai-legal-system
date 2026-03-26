from datetime import datetime, timezone

from app.core.enums import DocumentStatusEnum
from app.modules.common.documents.ingestion_service import DocumentIngestionService
from app.modules.common.documents.repository import FileDocumentRepository
from app.modules.common.documents.schemas import DocumentRecord
from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.common.qdrant.client import QdrantVectorStore
from app.modules.common.qdrant.schemas import ReindexResponse


class CollectionReindexService:
    def __init__(
        self,
        document_repository: FileDocumentRepository,
        ingestion_service: DocumentIngestionService,
        embedding_service: EmbeddingService,
        vector_store: QdrantVectorStore,
    ) -> None:
        self.document_repository = document_repository
        self.ingestion_service = ingestion_service
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    def reindex(self, delete_previous_collection: bool = False) -> ReindexResponse:
        profile = self.embedding_service.profile
        source_collection = self.vector_store.get_active_collection_name()
        target_collection = self.vector_store.create_next_collection_for_profile(profile)

        records = self.document_repository.list()
        reindexed_count = 0
        for record in records:
            embedded_chunks, chunk_count = self.ingestion_service.build_embedded_chunks(record)
            self.vector_store.upsert_chunks(
                chunks=embedded_chunks,
                vector_size=profile.dimension,
                collection_name=target_collection,
            )
            self._save_reindexed_record(record, chunk_count)
            reindexed_count += 1

        self.vector_store.switch_alias(target_collection)
        if source_collection and source_collection != target_collection and delete_previous_collection:
            self.vector_store.delete_collection(source_collection)

        return ReindexResponse(
            status="completed",
            alias_name=self.vector_store.alias_name,
            source_collection=source_collection,
            target_collection=target_collection,
            documents_total=len(records),
            documents_reindexed=reindexed_count,
        )

    def _save_reindexed_record(self, record: DocumentRecord, chunk_count: int) -> None:
        updated = record.model_copy(
            update={
                "status": DocumentStatusEnum.INGESTED,
                "chunk_count": chunk_count,
                "ingested_at": datetime.now(timezone.utc),
                "error_message": None,
            }
        )
        self.document_repository.save(updated)
