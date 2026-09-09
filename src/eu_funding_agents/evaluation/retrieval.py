from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalMetrics:
    recall_at_5: float
    recall_at_10: float
    precision_at_5: float
    mrr: float
    ndcg_at_5: float
    ndcg_at_10: float


def _recall(ranked: list[str], relevance: dict[str, float], k: int) -> float:
    relevant = {item for item, grade in relevance.items() if grade > 0}
    if not relevant:
        return 0.0
    return len(relevant.intersection(ranked[:k])) / len(relevant)


def _precision(ranked: list[str], relevance: dict[str, float], k: int) -> float:
    if k < 1:
        raise ValueError("k must be positive")
    return sum(relevance.get(item, 0) > 0 for item in ranked[:k]) / k


def _ndcg(ranked: list[str], relevance: dict[str, float], k: int) -> float:
    def dcg(grades: list[float]) -> float:
        return sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, 1))

    actual = dcg([relevance.get(item, 0) for item in ranked[:k]])
    ideal = dcg(sorted(relevance.values(), reverse=True)[:k])
    return actual / ideal if ideal else 0.0


def retrieval_metrics(ranked: list[str], relevance: dict[str, float]) -> RetrievalMetrics:
    reciprocal_rank = next(
        (1.0 / rank for rank, item in enumerate(ranked, 1) if relevance.get(item, 0) > 0),
        0.0,
    )
    return RetrievalMetrics(
        recall_at_5=_recall(ranked, relevance, 5),
        recall_at_10=_recall(ranked, relevance, 10),
        precision_at_5=_precision(ranked, relevance, 5),
        mrr=reciprocal_rank,
        ndcg_at_5=_ndcg(ranked, relevance, 5),
        ndcg_at_10=_ndcg(ranked, relevance, 10),
    )
