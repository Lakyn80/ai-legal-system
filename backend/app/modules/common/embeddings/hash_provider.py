import hashlib
import math
import re
import unicodedata


class DeterministicHashEmbeddingProvider:
    revision = "deterministic_hash_v2"

    def __init__(self, dimension: int = 384) -> None:
        self._dimension = max(32, dimension)
        self.model_name = f"deterministic-hash-{self._dimension}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        tokens = self._tokenize(text)
        vector = [0.0] * self._dimension

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + (digest[5] / 255.0)
            vector[index] += sign * weight

        return self._normalize(vector)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        normalized = DeterministicHashEmbeddingProvider._normalize_text(text)
        if not normalized:
            return ["__empty__"]
        return re.findall(r"\w+", normalized, flags=re.UNICODE) or [normalized]

    @staticmethod
    def _normalize_text(text: str) -> str:
        decomposed = unicodedata.normalize("NFKD", text.strip().lower())
        return "".join(character for character in decomposed if not unicodedata.combining(character))

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return [0.0 for _ in vector]
        return [value / norm for value in vector]
