from typing import List


def filter_by_score(results: List, min_score: float = 0.9):
    return [result for result in results if result.score >= min_score]
