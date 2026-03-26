import hashlib
import re
import unicodedata


class QueryNormalizer:
    def normalize(self, query: str) -> str:
        normalized = unicodedata.normalize("NFKC", query).lower().strip()
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def keyword_terms(self, query: str) -> list[str]:
        normalized = self._normalize_for_terms(query)
        return [token for token in re.findall(r"\w+", normalized, flags=re.UNICODE) if len(token) > 2]

    def hash_query(self, normalized_query: str) -> str:
        return hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()

    def _normalize_for_terms(self, query: str) -> str:
        decomposed = unicodedata.normalize("NFKD", self.normalize(query))
        return "".join(character for character in decomposed if not unicodedata.combining(character))
