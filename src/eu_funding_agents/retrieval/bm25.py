from __future__ import annotations

import re
import unicodedata

from rank_bm25 import BM25Okapi

from eu_funding_agents.retrieval.types import SearchDocument, SearchResult

TOKEN_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return TOKEN_PATTERN.findall(normalized)


class BM25Retriever:
    def __init__(self, documents: list[SearchDocument]) -> None:
        if not documents:
            raise ValueError("BM25 requires at least one document")
        self._documents = documents
        self._index = BM25Okapi([tokenize(document.text) for document in documents])

    def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scored = zip(self._documents, self._index.get_scores(query_tokens), strict=True)
        ranked = sorted(scored, key=lambda item: (-float(item[1]), item[0].call_id))[:top_k]
        return [
            SearchResult(
                call_id=document.call_id,
                title=document.title,
                programme=document.programme,
                official_url=document.official_url,
                score=float(score),
                components={"bm25": float(score)},
            )
            for document, score in ranked
        ]
