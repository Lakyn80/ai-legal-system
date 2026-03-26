from datetime import datetime, timezone
from enum import Enum

from app.core.enums import DocumentStatusEnum
from app.core.exceptions import DocumentProcessingError
from app.modules.common.chunking.service import TextChunkingService
from app.modules.common.documents.repository import FileDocumentRepository
from app.modules.common.documents.schemas import DocumentIngestionResult, DocumentRecord
from app.modules.common.embeddings.provider import EmbeddingService
from app.modules.common.parsing.service import DocumentParserService
from app.modules.common.qdrant.client import QdrantVectorStore
from app.modules.common.qdrant.schemas import ChunkPayload, EmbeddedChunk


class DocumentIngestionService:
    def __init__(
        self,
        document_repository: FileDocumentRepository,
        parser_service: DocumentParserService,
        chunking_service: TextChunkingService,
        embedding_service: EmbeddingService,
        vector_store: QdrantVectorStore,
    ) -> None:
        self.document_repository = document_repository
        self.parser_service = parser_service
        self.chunking_service = chunking_service
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    def ingest_documents(self, document_ids: list[str]) -> list[DocumentIngestionResult]:
        if document_ids:
            records = [
                record
                for document_id in document_ids
                if (record := self.document_repository.get(document_id)) is not None
            ]
        else:
            records = self.document_repository.list()

        return [self.ingest_record(record) for record in records]

    def ingest_record(self, record: DocumentRecord) -> DocumentIngestionResult:
        try:
            embedded_chunks, chunk_count = self.build_embedded_chunks(record)
            self.vector_store.ensure_active_collection(self.embedding_service.profile)
            self.vector_store.upsert_chunks(
                chunks=embedded_chunks,
                vector_size=self.embedding_service.dimension,
            )

            updated = record.model_copy(
                update={
                    "status": DocumentStatusEnum.INGESTED,
                    "chunk_count": chunk_count,
                    "ingested_at": datetime.now(timezone.utc),
                    "error_message": None,
                }
            )
            self.document_repository.save(updated)
            return DocumentIngestionResult(
                document_id=record.id,
                filename=record.filename,
                status=DocumentStatusEnum.INGESTED.value,
                chunk_count=chunk_count,
            )
        except Exception as exc:
            failed = record.model_copy(
                update={
                    "status": DocumentStatusEnum.FAILED,
                    "error_message": str(exc),
                }
            )
            self.document_repository.save(failed)
            return DocumentIngestionResult(
                document_id=record.id,
                filename=record.filename,
                status=DocumentStatusEnum.FAILED.value,
                error=str(exc),
            )

    def build_embedded_chunks(self, record: DocumentRecord) -> tuple[list[EmbeddedChunk], int]:
        text = self.parser_service.parse(record)
        chunks = self.chunking_service.chunk_text(text)
        if not chunks:
            raise DocumentProcessingError("Document did not produce any text chunks.")

        vectors = self.embedding_service.embed_documents(chunks)
        embedded_chunks = [
            EmbeddedChunk(
                id=f"{record.id}:{index}",
                vector=vector,
                payload=ChunkPayload(
                    chunk_id=f"{record.id}:{index}",
                    document_id=record.id,
                    filename=record.filename,
                    country=record.country,
                    domain=record.domain,
                    jurisdiction_module=self._enum_value(record.country),
                    text=chunk,
                    chunk_index=index,
                    source_type=record.document_type,
                    source=record.source,
                    case_id=record.case_id,
                    tags=record.tags,
                ),
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
        return embedded_chunks, len(chunks)

    @staticmethod
    def _enum_value(value: Enum | str) -> str:
        return value.value if isinstance(value, Enum) else str(value)
