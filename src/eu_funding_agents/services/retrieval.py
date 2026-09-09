from __future__ import annotations

from pathlib import Path

from eu_funding_agents.retrieval.bm25 import BM25Retriever
from eu_funding_agents.retrieval.dense import (
    DEFAULT_MODEL,
    DEFAULT_MODEL_REVISION,
    DenseRetriever,
    SentenceEncoder,
)
from eu_funding_agents.retrieval.fusion import reciprocal_rank_fusion
from eu_funding_agents.retrieval.types import SearchDocument, SearchResult


class MultilingualHybridRetriever:
    method = "hybrid_multilingual"

    def __init__(self, encoder: SentenceEncoder, *, cache_dir: Path) -> None:
        self._encoder = encoder
        self._cache_dir = cache_dir

    def search(
        self,
        documents: list[SearchDocument],
        query: str,
        *,
        top_k: int,
    ) -> list[SearchResult]:
        candidate_depth = max(50, top_k)
        bm25_results = [
            result
            for result in BM25Retriever(documents).search(query, top_k=candidate_depth)
            if result.score > 0
        ]
        dense = DenseRetriever.from_encoder(
            documents,
            self._encoder,
            model_name=DEFAULT_MODEL,
            revision=DEFAULT_MODEL_REVISION,
            cache_dir=self._cache_dir,
        )
        dense_results = dense.search(query, top_k=candidate_depth)
        return reciprocal_rank_fusion(
            {"bm25": bm25_results, "dense": dense_results},
            top_k=top_k,
        )
