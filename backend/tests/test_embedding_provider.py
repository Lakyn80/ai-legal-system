import pytest

from app.modules.common.embeddings.profile import EmbeddingProfile
from app.modules.common.embeddings.provider import EmbeddingService


def test_hash_embedding_provider_returns_consistent_vectors():
    service = EmbeddingService(
        model_name="unused",
        provider_name="hash",
        fallback_provider_name=None,
        hash_dimension=64,
    )

    first = service.embed_query("Obcansky zakonik a smluvni vztahy")
    second = service.embed_query("Obcansky zakonik a smluvni vztahy")

    assert len(first) == 64
    assert first == second


def test_hash_embedding_provider_normalizes_diacritics():
    service = EmbeddingService(
        model_name="unused",
        provider_name="hash",
        fallback_provider_name=None,
        hash_dimension=64,
    )

    plain = service.embed_query("obcansky zakonik")
    accented = service.embed_query("občanský zákoník")

    assert plain == accented


def test_embedding_service_supports_sentence_transformer_alias(monkeypatch):
    class FakeSentenceTransformerProvider:
        revision = "sentence_transformer_v1"
        dimension = 3

        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2, 0.3] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [0.1, 0.2, 0.3]

    monkeypatch.setattr(
        "app.modules.common.embeddings.provider.SentenceTransformerEmbeddingProvider",
        FakeSentenceTransformerProvider,
    )

    service = EmbeddingService(
        model_name="Alibaba-NLP/gte-multilingual-base",
        provider_name="sentence_transformer",
        fallback_provider_name="hash",
        hash_dimension=32,
    )

    assert service.embed_query("spor o nahradu skody") == [0.1, 0.2, 0.3]
    assert service.profile == EmbeddingProfile(
        provider="sentence_transformer",
        model="Alibaba-NLP/gte-multilingual-base",
        dimension=3,
        revision="sentence_transformer_v1",
    )


def test_embedding_service_does_not_runtime_fallback_when_sentence_provider_fails(monkeypatch):
    class BrokenSentenceTransformerProvider:
        revision = "sentence_transformer_v1"

        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        @property
        def dimension(self) -> int:
            raise RuntimeError("model download unavailable")

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("model download unavailable")

        def embed_query(self, text: str) -> list[float]:
            raise RuntimeError("model download unavailable")

    monkeypatch.setattr(
        "app.modules.common.embeddings.provider.SentenceTransformerEmbeddingProvider",
        BrokenSentenceTransformerProvider,
    )

    service = EmbeddingService(
        model_name="Alibaba-NLP/gte-multilingual-base",
        provider_name="sentence_transformer",
        fallback_provider_name="hash",
        hash_dimension=32,
    )

    with pytest.raises(RuntimeError, match="model download unavailable"):
        service.embed_query("spor o nahradu skody")

    assert service.provider_name == "sentence_transformer"
