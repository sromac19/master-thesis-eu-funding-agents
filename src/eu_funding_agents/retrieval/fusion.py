from __future__ import annotations

from collections import defaultdict

from eu_funding_agents.retrieval.types import SearchResult


def reciprocal_rank_fusion(
    result_sets: dict[str, list[SearchResult]], *, top_k: int = 10, rank_constant: int = 60
) -> list[SearchResult]:
    if top_k < 1 or rank_constant < 1:
        raise ValueError("top_k and rank_constant must be positive")
    scores: dict[str, float] = defaultdict(float)
    components: dict[str, dict[str, float]] = defaultdict(dict)
    documents: dict[str, SearchResult] = {}
    for method, results in sorted(result_sets.items()):
        seen: set[str] = set()
        for rank, result in enumerate(results, start=1):
            if result.call_id in seen:
                continue
            seen.add(result.call_id)
            contribution = 1.0 / (rank_constant + rank)
            scores[result.call_id] += contribution
            components[result.call_id][method] = contribution
            documents[result.call_id] = result
    ranked_ids = sorted(scores, key=lambda call_id: (-scores[call_id], call_id))[:top_k]
    return [
        SearchResult(
            call_id=call_id,
            title=documents[call_id].title,
            programme=documents[call_id].programme,
            official_url=documents[call_id].official_url,
            score=scores[call_id],
            components=components[call_id],
        )
        for call_id in ranked_ids
    ]
