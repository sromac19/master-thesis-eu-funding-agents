from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Protocol

from eu_funding_agents.retrieval.types import SearchDocument, SearchResult

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


class EmbeddingMatrix(Protocol):
    def __getitem__(self, index: int) -> Sequence[float]: ...

    def __matmul__(self, vector: Sequence[float]) -> Iterable[float]: ...


class SentenceEncoder(Protocol):
    def encode(self, sentences: list[str], *, normalize_embeddings: bool) -> EmbeddingMatrix: ...


class DenseRetriever:
    def __init__(
        self,
        documents: list[SearchDocument],
        encoder: SentenceEncoder,
        *,
        embeddings: EmbeddingMatrix | None = None,
    ) -> None:
        if not documents:
            raise ValueError("Dense retrieval requires at least one document")
        self._documents = documents
        self._encoder = encoder
        self._embeddings = (
            embeddings
            if embeddings is not None
            else encoder.encode(
                [document.text for document in documents], normalize_embeddings=True
            )
        )

    @classmethod
    def from_pretrained(
        cls,
        documents: list[SearchDocument],
        *,
        model_name: str = DEFAULT_MODEL,
        revision: str = DEFAULT_MODEL_REVISION,
        cache_dir: Path | None = None,
    ) -> DenseRetriever:
        from sentence_transformers import SentenceTransformer

        encoder = SentenceTransformer(model_name, revision=revision)
        return cls.from_encoder(
            documents,
            encoder,
            model_name=model_name,
            revision=revision,
            cache_dir=cache_dir,
        )

    @classmethod
    def from_encoder(
        cls,
        documents: list[SearchDocument],
        encoder: SentenceEncoder,
        *,
        model_name: str = DEFAULT_MODEL,
        revision: str = DEFAULT_MODEL_REVISION,
        cache_dir: Path | None = None,
    ) -> DenseRetriever:
        import numpy as np

        if cache_dir is None:
            return cls(documents, encoder)

        corpus_digest = hashlib.sha256(
            "\n".join(f"{item.call_id}\t{item.text}" for item in documents).encode()
        ).hexdigest()
        model_digest = hashlib.sha256(f"{model_name}@{revision}".encode()).hexdigest()[:16]
        cache_path = cache_dir / f"{model_digest}-{corpus_digest}.npy"
        cache_dir.mkdir(parents=True, exist_ok=True)
        if cache_path.exists():
            embeddings = np.load(cache_path, mmap_mode="r")
        else:
            embeddings = encoder.encode(
                [document.text for document in documents], normalize_embeddings=True
            )
            temporary_path = cache_path.with_suffix(".tmp.npy")
            np.save(temporary_path, embeddings)
            temporary_path.replace(cache_path)
        return cls(documents, encoder, embeddings=embeddings)

    def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return self.search_many([query], top_k=top_k)[0]

    def search_many(self, queries: list[str], *, top_k: int = 10) -> list[list[SearchResult]]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if not queries:
            return []
        query_embeddings = self._encoder.encode(queries, normalize_embeddings=True)
        results: list[list[SearchResult]] = []
        for query_embedding in query_embeddings:
            scores = self._embeddings @ query_embedding
            ranked = sorted(
                zip(self._documents, scores, strict=True),
                key=lambda item: (-float(item[1]), item[0].call_id),
            )[:top_k]
            results.append(
                [
                    SearchResult(
                        call_id=document.call_id,
                        title=document.title,
                        programme=document.programme,
                        official_url=document.official_url,
                        score=float(score),
                        components={"dense": float(score)},
                    )
                    for document, score in ranked
                ]
            )
        return results
