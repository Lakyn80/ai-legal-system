from __future__ import annotations

# Passthrough stub — CzechLawReranker inside the retrieval pipeline handles re-ranking.
# CrossEncoder model is not loaded to avoid startup download dependency.


def warmup_reranker() -> None:
    pass


def rerank(query: str, results: list) -> list:
    return results
