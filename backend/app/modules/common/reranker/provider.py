from __future__ import annotations

from abc import ABC, abstractmethod


class BaseRerankerProvider(ABC):
    """
    Scores (query, document) pairs and returns relevance scores.

    Implementations must be:
    - thread-safe (shared singleton, called from ThreadPoolExecutor)
    - fail-open (raise on unrecoverable errors, caller handles fallback)
    - CPU-compatible
    """

    @abstractmethod
    def score(self, query: str, documents: list[str]) -> list[float]:
        """
        Return a relevance score for each (query, document) pair.
        Length of returned list must equal length of documents.
        Higher score = more relevant.
        """
        raise NotImplementedError
