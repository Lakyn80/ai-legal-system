import hashlib

from pydantic import BaseModel


class EmbeddingProfile(BaseModel):
    provider: str
    model: str
    dimension: int
    revision: str

    @property
    def fingerprint(self) -> str:
        payload = f"{self.provider}|{self.model}|{self.dimension}|{self.revision}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

    def to_collection_metadata(self) -> dict[str, str | int]:
        return {
            "embedding_provider": self.provider,
            "embedding_model": self.model,
            "embedding_dim": self.dimension,
            "embedding_revision": self.revision,
            "embedding_fingerprint": self.fingerprint,
        }
