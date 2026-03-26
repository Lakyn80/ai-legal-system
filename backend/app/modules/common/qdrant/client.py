import re
from collections.abc import Mapping
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.core.exceptions import EmbeddingMismatchError
from app.modules.common.embeddings.profile import EmbeddingProfile
from app.modules.common.qdrant.schemas import (
    CollectionEmbeddingMetadata,
    EmbeddedChunk,
    SearchResultItem,
)


class QdrantVectorStore:
    def __init__(
        self,
        url: str,
        api_key: str | None,
        collection_name: str,
        alias_name: str | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.alias_name = alias_name or f"{collection_name}_active"
        self._client = QdrantClient(url=url, api_key=api_key)
        self._validated_fingerprint: str | None = None

    def ensure_active_collection(self, profile: EmbeddingProfile) -> None:
        if self._validated_fingerprint == profile.fingerprint:
            return

        active_collection = self.get_active_collection_name()
        if active_collection:
            self._validate_collection_metadata(active_collection, profile)
            self._validated_fingerprint = profile.fingerprint
            return

        latest_match = self._find_latest_collection_for_profile(profile)
        if latest_match:
            self.switch_alias(latest_match)
            self._validated_fingerprint = profile.fingerprint
            return

        if self.collection_exists(self.collection_name):
            if self._can_adopt_legacy_collection(self.collection_name, profile):
                self._update_collection_metadata(self.collection_name, profile)
                self.switch_alias(self.collection_name)
                self._validated_fingerprint = profile.fingerprint
                return
            if self._is_empty_collection(self.collection_name):
                target_collection = self.create_next_collection_for_profile(profile)
                self.switch_alias(target_collection)
                self._validated_fingerprint = profile.fingerprint
                return
            raise EmbeddingMismatchError("Embedding mismatch detected. Reindex required.")

        target_collection = self.create_next_collection_for_profile(profile)
        self.switch_alias(target_collection)
        self._validated_fingerprint = profile.fingerprint

    def create_next_collection_for_profile(self, profile: EmbeddingProfile) -> str:
        prefix = self._collection_prefix(profile)
        existing_versions = self._matching_collection_versions(prefix)
        next_version = max(existing_versions, default=0) + 1
        target_collection = f"{prefix}__v{next_version}"
        self._create_collection(target_collection, profile)
        return target_collection

    def switch_alias(self, target_collection: str) -> None:
        current_collection = self.get_active_collection_name()
        if current_collection == target_collection:
            return

        operations: list[object] = []

        if current_collection:
            operations.append(
                models.DeleteAliasOperation(
                    delete_alias=models.DeleteAlias(alias_name=self.alias_name)
                )
            )

        operations.append(
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(
                    collection_name=target_collection,
                    alias_name=self.alias_name,
                )
            )
        )
        self._client.update_collection_aliases(change_aliases_operations=operations)
        self._validated_fingerprint = None

    def get_active_collection_name(self) -> str | None:
        aliases = self._client.get_aliases().aliases
        for alias in aliases:
            if alias.alias_name == self.alias_name:
                return alias.collection_name
        return None

    def get_active_collection_metadata(self) -> CollectionEmbeddingMetadata | None:
        active_collection = self.get_active_collection_name()
        if not active_collection:
            return None
        return self._get_collection_metadata(active_collection)

    def upsert_chunks(
        self,
        chunks: list[EmbeddedChunk],
        vector_size: int,
        collection_name: str | None = None,
    ) -> None:
        if not chunks:
            return

        target_collection = collection_name or self.alias_name
        points = [
            models.PointStruct(
                id=self._normalize_point_id(chunk.id),
                vector=chunk.vector,
                payload=chunk.payload.model_dump(mode="json"),
            )
            for chunk in chunks
        ]
        self._client.upsert(collection_name=target_collection, points=points)

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        country: str | None = None,
        domain: str | None = None,
        document_ids: list[str] | None = None,
        case_id: str | None = None,
    ) -> list[SearchResultItem]:
        query_filter = self._build_filter(
            country=country,
            domain=domain,
            document_ids=document_ids,
            case_id=case_id,
        )

        if hasattr(self._client, "query_points"):
            response = self._client.query_points(
                collection_name=self.alias_name,
                query=query_vector,
                limit=top_k,
                query_filter=query_filter,
            )
            points = response.points
        else:
            points = self._client.search(
                collection_name=self.alias_name,
                query_vector=query_vector,
                limit=top_k,
                query_filter=query_filter,
            )

        results: list[SearchResultItem] = []
        for point in points:
            payload = point.payload or {}
            results.append(
                SearchResultItem(
                    chunk_id=payload["chunk_id"],
                    document_id=payload["document_id"],
                    filename=payload["filename"],
                    country=payload["country"],
                    domain=payload["domain"],
                    jurisdiction_module=payload["jurisdiction_module"],
                    text=payload["text"],
                    chunk_index=payload["chunk_index"],
                    source_type=payload["source_type"],
                    source=payload.get("source"),
                    case_id=payload.get("case_id"),
                    tags=payload.get("tags", []),
                    score=float(point.score),
                )
            )
        return results

    def delete_collection(self, collection_name: str) -> None:
        if self.collection_exists(collection_name):
            self._client.delete_collection(collection_name=collection_name)
            if self.get_active_collection_name() == collection_name:
                self._validated_fingerprint = None

    def health_check(self) -> bool:
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False

    def collection_exists(self, collection_name: str) -> bool:
        return self._client.collection_exists(collection_name=collection_name)

    def _validate_collection_metadata(self, collection_name: str, profile: EmbeddingProfile) -> None:
        metadata = self._get_collection_metadata(collection_name)
        if metadata is None:
            if self._can_adopt_legacy_collection(collection_name, profile):
                self._update_collection_metadata(collection_name, profile)
                return
            raise EmbeddingMismatchError("Embedding mismatch detected. Reindex required.")

        if metadata.embedding_fingerprint != profile.fingerprint:
            if self._can_adopt_legacy_collection(collection_name, profile):
                self._update_collection_metadata(collection_name, profile)
                return
            raise EmbeddingMismatchError("Embedding mismatch detected. Reindex required.")

    def _find_latest_collection_for_profile(self, profile: EmbeddingProfile) -> str | None:
        prefix = self._collection_prefix(profile)
        matching_collections = self._matching_collection_versions(prefix)
        if not matching_collections:
            return None

        latest_version = max(matching_collections)
        target = f"{prefix}__v{latest_version}"
        self._validate_collection_metadata(target, profile)
        return target

    def _matching_collection_versions(self, prefix: str) -> list[int]:
        versions: list[int] = []
        for collection_name in self._list_collection_names():
            if not collection_name.startswith(prefix + "__v"):
                continue
            match = re.search(r"__v(\d+)$", collection_name)
            if match:
                versions.append(int(match.group(1)))
        return versions

    def _create_collection(self, collection_name: str, profile: EmbeddingProfile) -> None:
        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=profile.dimension,
                distance=models.Distance.COSINE,
            ),
            metadata=profile.to_collection_metadata(),
        )

    def _update_collection_metadata(self, collection_name: str, profile: EmbeddingProfile) -> None:
        self._client.update_collection(
            collection_name=collection_name,
            metadata=profile.to_collection_metadata(),
        )

    def _get_collection_metadata(self, collection_name: str) -> CollectionEmbeddingMetadata | None:
        info = self._client.get_collection(collection_name=collection_name)
        raw_metadata = getattr(info.config, "metadata", None)
        if not raw_metadata:
            return None
        if isinstance(raw_metadata, Mapping):
            return CollectionEmbeddingMetadata.model_validate(dict(raw_metadata))
        return CollectionEmbeddingMetadata.model_validate(raw_metadata)

    def _can_adopt_legacy_collection(self, collection_name: str, profile: EmbeddingProfile) -> bool:
        info = self._client.get_collection(collection_name=collection_name)
        metadata = self._get_collection_metadata(collection_name)

        if metadata is not None:
            if metadata.embedding_fingerprint == profile.fingerprint:
                return True
            return (
                profile.provider == "hash"
                and metadata.embedding_provider == "hash"
                and metadata.embedding_dim == profile.dimension
                and metadata.embedding_revision == profile.revision
            )

        points_count = getattr(info, "points_count", 0) or 0
        vector_size = self._extract_vector_size(info)

        if points_count == 0:
            return vector_size == profile.dimension

        return collection_name == self.collection_name and profile.provider == "hash" and vector_size == profile.dimension

    def _is_empty_collection(self, collection_name: str) -> bool:
        info = self._client.get_collection(collection_name=collection_name)
        return (getattr(info, "points_count", 0) or 0) == 0

    def _extract_vector_size(self, info) -> int:
        vectors = info.config.params.vectors
        if hasattr(vectors, "size"):
            return int(vectors.size)
        if isinstance(vectors, Mapping):
            first_value = next(iter(vectors.values()))
            return int(first_value.size)
        raise EmbeddingMismatchError("Unable to determine collection vector size.")

    def _list_collection_names(self) -> list[str]:
        return [collection.name for collection in self._client.get_collections().collections]

    def _collection_prefix(self, profile: EmbeddingProfile) -> str:
        provider_slug = profile.provider.replace("-", "_")
        return f"{self.collection_name}__{provider_slug}__{profile.fingerprint}"

    @staticmethod
    def _build_filter(
        country: str | None,
        domain: str | None,
        document_ids: list[str] | None,
        case_id: str | None,
    ) -> models.Filter | None:
        conditions: list[models.FieldCondition] = []

        if country:
            conditions.append(
                models.FieldCondition(key="country", match=models.MatchValue(value=country))
            )
        if domain:
            conditions.append(
                models.FieldCondition(key="domain", match=models.MatchValue(value=domain))
            )
        if document_ids:
            conditions.append(
                models.FieldCondition(key="document_id", match=models.MatchAny(any=document_ids))
            )
        if case_id:
            conditions.append(
                models.FieldCondition(key="case_id", match=models.MatchValue(value=case_id))
            )

        if not conditions:
            return None
        return models.Filter(must=conditions)

    @staticmethod
    def _normalize_point_id(value: str) -> str | int:
        try:
            return str(uuid5(NAMESPACE_URL, value))
        except Exception:
            return value
