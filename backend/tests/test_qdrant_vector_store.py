from types import SimpleNamespace

import pytest

from app.core.exceptions import EmbeddingMismatchError
from app.modules.common.embeddings.profile import EmbeddingProfile
from app.modules.common.qdrant.client import QdrantVectorStore


class FakeCollectionInfo:
    def __init__(self, size: int, metadata: dict | None = None, points_count: int = 0) -> None:
        self.points_count = points_count
        self.config = SimpleNamespace(
            params=SimpleNamespace(vectors=SimpleNamespace(size=size)),
            metadata=metadata,
        )


class FakeQdrantClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollectionInfo] = {}
        self.aliases: dict[str, str] = {}

    def get_collections(self):
        return SimpleNamespace(
            collections=[SimpleNamespace(name=name) for name in sorted(self.collections.keys())]
        )

    def get_aliases(self):
        return SimpleNamespace(
            aliases=[
                SimpleNamespace(alias_name=alias_name, collection_name=collection_name)
                for alias_name, collection_name in self.aliases.items()
            ]
        )

    def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def get_collection(self, collection_name: str):
        return self.collections[collection_name]

    def create_collection(self, collection_name: str, vectors_config, metadata=None, **kwargs):
        self.collections[collection_name] = FakeCollectionInfo(
            size=vectors_config.size,
            metadata=metadata,
        )
        return True

    def update_collection(self, collection_name: str, metadata=None, **kwargs):
        current = self.collections[collection_name]
        merged_metadata = dict(current.config.metadata or {})
        merged_metadata.update(metadata or {})
        current.config.metadata = merged_metadata
        return True

    def update_collection_aliases(self, change_aliases_operations, **kwargs):
        for operation in change_aliases_operations:
            if hasattr(operation, "delete_alias") and operation.delete_alias is not None:
                self.aliases.pop(operation.delete_alias.alias_name, None)
            if hasattr(operation, "create_alias") and operation.create_alias is not None:
                self.aliases[operation.create_alias.alias_name] = operation.create_alias.collection_name
        return True

    def delete_collection(self, collection_name: str):
        self.collections.pop(collection_name, None)
        return True

    def upsert(self, collection_name: str, points):
        return True


def build_store(client: FakeQdrantClient) -> QdrantVectorStore:
    store = QdrantVectorStore(
        url="http://qdrant:6333",
        api_key=None,
        collection_name="legal_documents",
        alias_name="legal_documents_active",
    )
    store._client = client
    return store


def build_profile(provider: str = "hash", dimension: int = 384) -> EmbeddingProfile:
    return EmbeddingProfile(
        provider=provider,
        model=(
            "Alibaba-NLP/gte-multilingual-base"
            if provider == "sentence_transformer"
            else f"deterministic-hash-{dimension}"
        ),
        dimension=dimension,
        revision="sentence_transformer_v1" if provider == "sentence_transformer" else "deterministic_hash_v2",
    )


def test_vector_store_bootstraps_alias_to_matching_collection():
    client = FakeQdrantClient()
    profile = build_profile()
    collection_name = f"legal_documents__hash__{profile.fingerprint}__v2"
    client.collections[collection_name] = FakeCollectionInfo(
        size=profile.dimension,
        metadata=profile.to_collection_metadata(),
        points_count=10,
    )
    store = build_store(client)

    store.ensure_active_collection(profile)

    assert client.aliases["legal_documents_active"] == collection_name


def test_vector_store_raises_on_embedding_mismatch():
    client = FakeQdrantClient()
    current_profile = build_profile(provider="sentence_transformer", dimension=768)
    old_profile = build_profile(provider="hash", dimension=384)
    old_collection = f"legal_documents__hash__{old_profile.fingerprint}__v1"
    client.collections[old_collection] = FakeCollectionInfo(
        size=old_profile.dimension,
        metadata=old_profile.to_collection_metadata(),
        points_count=10,
    )
    client.aliases["legal_documents_active"] = old_collection
    store = build_store(client)

    with pytest.raises(EmbeddingMismatchError, match="Reindex required"):
        store.ensure_active_collection(current_profile)


def test_vector_store_adopts_legacy_hash_collection_without_metadata():
    client = FakeQdrantClient()
    profile = build_profile(provider="hash", dimension=384)
    client.collections["legal_documents"] = FakeCollectionInfo(size=384, metadata=None, points_count=10)
    store = build_store(client)

    store.ensure_active_collection(profile)

    assert client.aliases["legal_documents_active"] == "legal_documents"
    assert client.collections["legal_documents"].config.metadata == profile.to_collection_metadata()


def test_vector_store_updates_legacy_hash_metadata_when_profile_signature_changes():
    client = FakeQdrantClient()
    current_profile = build_profile(provider="hash", dimension=384)
    legacy_profile = EmbeddingProfile(
        provider="hash",
        model="Alibaba-NLP/gte-multilingual-base",
        dimension=384,
        revision="deterministic_hash_v2",
    )
    collection_name = "legal_documents__hash__legacy__v1"
    client.collections[collection_name] = FakeCollectionInfo(
        size=384,
        metadata=legacy_profile.to_collection_metadata(),
        points_count=10,
    )
    client.aliases["legal_documents_active"] = collection_name
    store = build_store(client)

    store.ensure_active_collection(current_profile)

    assert client.collections[collection_name].config.metadata == current_profile.to_collection_metadata()
