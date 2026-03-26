from app.modules.common.embeddings.sentence_transformer_provider import (
    SentenceTransformerEmbeddingProvider,
)


class FakeVector:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def tolist(self) -> list[float]:
        return self.values


def test_sentence_transformer_provider_loads_lazily_and_uses_cpu(monkeypatch):
    calls: list[dict[str, object]] = []

    class FakeSentenceTransformer:
        def __init__(
            self,
            model_name_or_path: str,
            device: str | None = None,
            trust_remote_code: bool | None = None,
        ) -> None:
            calls.append(
                {
                    "model_name_or_path": model_name_or_path,
                    "device": device,
                    "trust_remote_code": trust_remote_code,
                }
            )

        def get_sentence_embedding_dimension(self) -> int:
            return 3

        def encode(self, texts, normalize_embeddings: bool = True):
            if isinstance(texts, list):
                return [FakeVector([0.1, 0.2, 0.3]) for _ in texts]
            return FakeVector([0.1, 0.2, 0.3])

    monkeypatch.setattr(
        "app.modules.common.embeddings.sentence_transformer_provider.SentenceTransformer",
        FakeSentenceTransformer,
    )

    provider = SentenceTransformerEmbeddingProvider("Alibaba-NLP/gte-multilingual-base")

    assert calls == []
    assert provider.embed_query("test query") == [0.1, 0.2, 0.3]
    assert calls == [
        {
            "model_name_or_path": "Alibaba-NLP/gte-multilingual-base",
            "device": "cpu",
            "trust_remote_code": True,
        }
    ]


def test_sentence_transformer_provider_raises_clear_error_on_load_failure(monkeypatch):
    class BrokenSentenceTransformer:
        def __init__(self, *args, **kwargs) -> None:
            raise ValueError("cannot load model")

    monkeypatch.setattr(
        "app.modules.common.embeddings.sentence_transformer_provider.SentenceTransformer",
        BrokenSentenceTransformer,
    )

    provider = SentenceTransformerEmbeddingProvider("Alibaba-NLP/gte-multilingual-base")

    try:
        provider.embed_query("test query")
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected RuntimeError to be raised")

    assert "Alibaba-NLP/gte-multilingual-base" in message
    assert "EMBEDDING_PROVIDER=hash" in message
