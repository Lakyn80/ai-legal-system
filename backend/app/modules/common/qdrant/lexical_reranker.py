import re
import unicodedata

from app.modules.common.qdrant.schemas import SearchResultItem


class LexicalReranker:
    _CITATION_PATTERN = re.compile(
        r"(§\s*\d+[a-zA-Z]*|\b(?:cl\.|čl\.|article|art\.)\s*\d+[a-zA-Z]*)",
        flags=re.IGNORECASE,
    )

    def rerank(self, query: str, results: list[SearchResultItem], top_k: int) -> list[SearchResultItem]:
        if not results:
            return []

        scored_results = [
            (
                score_data["combined_score"],
                score_data["overlap_count"],
                result.model_copy(update={"score": score_data["combined_score"]}),
            )
            for result in results
            for score_data in [self.score_result(query, result)]
        ]
        scored_results.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored_results[:top_k]]

    def score_result(self, query: str, result: SearchResultItem) -> dict[str, float | bool | int]:
        query_terms = self._tokenize(query)
        if not query_terms:
            return {
                "combined_score": float(result.score),
                "lexical_score": 0.0,
                "overlap_count": 0,
                "overlap_ratio": 0.0,
                "phrase_match": False,
                "citation_match": False,
                "filename_match": False,
                "source_match": False,
            }

        normalized_query = self._normalize(query)
        query_term_set = set(query_terms)
        query_phrase = " ".join(query_terms)
        combined_text = "\n".join(part for part in [result.filename, result.source or "", result.text] if part)
        normalized_text = self._normalize(combined_text)
        text_terms = set(self._tokenize(combined_text))
        overlap_count = len(query_term_set & text_terms)
        overlap_ratio = overlap_count / max(1, len(query_term_set))
        phrase_match = bool(query_phrase and query_phrase in normalized_text)
        citation_match = bool(self._CITATION_PATTERN.search(normalized_query) and self._CITATION_PATTERN.search(normalized_text))
        filename_match = any(term in self._normalize(result.filename) for term in query_term_set)
        source_match = bool(result.source and any(term in self._normalize(result.source) for term in query_term_set))

        lexical_score = (
            overlap_ratio * 0.6
            + (0.2 if phrase_match else 0.0)
            + (0.15 if citation_match else 0.0)
            + (0.1 if filename_match else 0.0)
            + (0.05 if source_match else 0.0)
        )
        combined_score = float(result.score) + lexical_score

        return {
            "combined_score": combined_score,
            "lexical_score": lexical_score,
            "overlap_count": overlap_count,
            "overlap_ratio": overlap_ratio,
            "phrase_match": phrase_match,
            "citation_match": citation_match,
            "filename_match": filename_match,
            "source_match": source_match,
        }

    def extract_query_terms(self, query: str) -> list[str]:
        return self._tokenize(query)

    def query_has_citation(self, query: str) -> bool:
        return bool(self._CITATION_PATTERN.search(self._normalize(query)))

    def _tokenize(self, text: str) -> list[str]:
        normalized = self._normalize(text)
        return [token for token in re.findall(r"\w+", normalized, flags=re.UNICODE) if len(token) > 2]

    @staticmethod
    def _normalize(text: str) -> str:
        decomposed = unicodedata.normalize("NFKD", text.lower())
        return "".join(character for character in decomposed if not unicodedata.combining(character))
