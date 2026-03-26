from app.modules.common.embeddings.profile import EmbeddingProfile
from app.modules.common.embeddings.base import EmbeddingProvider
from app.modules.common.embeddings.hash_provider import DeterministicHashEmbeddingProvider
from app.modules.common.embeddings.sentence_transformer_provider import (
    SentenceTransformerEmbeddingProvider,
)


class EmbeddingService:
    def __init__(
        self,
        model_name: str,
        provider_name: str = "hash",
        fallback_provider_name: str | None = "hash",
        hash_dimension: int = 384,
    ) -> None:
        self.model_name = model_name
        self.provider_name = self._normalize_provider_name(provider_name)
        self.fallback_provider_name = (
            self._normalize_provider_name(fallback_provider_name)
            if fallback_provider_name is not None
            else None
        )
        self.hash_dimension = hash_dimension
        self._provider = self._build_provider(
            provider_name=self.provider_name,
            model_name=model_name,
            hash_dimension=hash_dimension,
        )

    @property
    def dimension(self) -> int:
        return self._provider.dimension

    @property
    def profile(self) -> EmbeddingProfile:
        return EmbeddingProfile(
            provider=self.provider_name,
            model=getattr(self._provider, "model_name", self.model_name),
            dimension=self.dimension,
            revision=self._provider.revision,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._provider.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._provider.embed_query(text)

    @staticmethod
    def _build_provider(
        provider_name: str,
        model_name: str,
        hash_dimension: int,
    ) -> EmbeddingProvider:
        normalized = EmbeddingService._normalize_provider_name(provider_name)
        if normalized in {"sentence_transformer", "sentence_transformers"}:
            return SentenceTransformerEmbeddingProvider(model_name=model_name)
        if normalized == "hash":
            return DeterministicHashEmbeddingProvider(dimension=hash_dimension)
        raise ValueError(f"Unsupported embedding provider: {provider_name}")

    @staticmethod
    def _normalize_provider_name(provider_name: str) -> str:
        normalized = provider_name.strip().lower()
        if normalized in {"sentence_transformer", "sentence_transformers"}:
            return "sentence_transformer"
        return normalized
