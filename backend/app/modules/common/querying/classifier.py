import re

from app.core.enums import DomainEnum
from app.modules.common.querying.schemas import QueryType


class QueryClassifier:
    _CITATION_PATTERNS = (
        re.compile(r"§\s*\d+[a-zA-Z]*", flags=re.IGNORECASE),
        re.compile(r"\b(?:cl\.|čl\.|article|art\.)\s*\d+[a-zA-Z]*", flags=re.IGNORECASE),
    )
    _CASE_PATTERNS = (
        re.compile(r"\bsp\.\s*zn\.", flags=re.IGNORECASE),
        re.compile(r"\bč\.\s*j\.", flags=re.IGNORECASE),
        re.compile(r"\bcase\s+no\.?\b", flags=re.IGNORECASE),
        re.compile(r"\b\d+\s*[a-z]{1,4}\s*\d+/\d{2,4}\b", flags=re.IGNORECASE),
    )
    _STRATEGY_KEYWORDS = {
        "strategie",
        "strategy",
        "spor",
        "sporu",
        "sporni",
        "argument",
        "argumenty",
        "obrana",
        "obhajoba",
        # "narok" / "naroku" intentionally excluded:
        # "nárok" is a basic Czech legal term (entitlement/right) that appears in
        # ordinary informational queries like "zaměstnanec nárok na odstupné".
        # Routing those to strategy_answer is wrong — they need law retrieval.
        "riziko",
        "risk",
        "claim",
        "позиция",
        "спор",
        "иск",
        "аргумент",
    }
    _LAW_KEYWORDS = {
        "zakon",
        "zakonik",
        "ustanoveni",
        "obcansky",
        "codex",
        "law",
        "article",
        "section",
        "paragraf",
        "статья",
        "закон",
        "кодекс",
    }
    _COURT_KEYWORDS = {
        "soud",
        "soudni",
        "rozsudek",
        "usneseni",
        "judikatura",
        "rozhodnuti",
        "court",
        "judgment",
        "decision",
        "case",
        "суд",
        "решение",
        "постановление",
    }

    def classify(self, normalized_query: str, keyword_terms: list[str]) -> QueryType:
        if self._contains_strategy_terms(keyword_terms):
            return QueryType.STRATEGY
        if self.find_citation_patterns(normalized_query):
            return QueryType.EXACT_STATUTE
        if self._contains_case_pattern(normalized_query) or self._contains_court_terms(keyword_terms):
            return QueryType.CASE_LOOKUP
        return QueryType.SEMANTIC_LAW

    def detect_domain(self, normalized_query: str, keyword_terms: list[str], query_type: QueryType) -> DomainEnum | None:
        if query_type == QueryType.STRATEGY:
            return None

        has_law = bool(self.find_citation_patterns(normalized_query)) or self._contains_law_terms(keyword_terms)
        has_court = self._contains_case_pattern(normalized_query) or self._contains_court_terms(keyword_terms)

        if has_law and not has_court:
            return DomainEnum.LAW
        if has_court and not has_law:
            return DomainEnum.COURTS
        if query_type == QueryType.CASE_LOOKUP:
            return DomainEnum.COURTS
        return DomainEnum.LAW

    def find_citation_patterns(self, normalized_query: str) -> list[str]:
        matches: list[str] = []
        for pattern in self._CITATION_PATTERNS:
            matches.extend(match.group(0) for match in pattern.finditer(normalized_query))
        return matches

    def _contains_case_pattern(self, normalized_query: str) -> bool:
        return any(pattern.search(normalized_query) for pattern in self._CASE_PATTERNS)

    def _contains_strategy_terms(self, keyword_terms: list[str]) -> bool:
        return any(term in self._STRATEGY_KEYWORDS for term in keyword_terms)

    def _contains_law_terms(self, keyword_terms: list[str]) -> bool:
        return any(term in self._LAW_KEYWORDS for term in keyword_terms)

    def _contains_court_terms(self, keyword_terms: list[str]) -> bool:
        return any(term in self._COURT_KEYWORDS for term in keyword_terms)
