from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from eu_funding_agents.config import Settings
from eu_funding_agents.retrieval.types import SearchDocument, SearchResult

DEFAULT_RERANKER = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
DEFAULT_RERANKER_REVISION = "1427fd652930e4ba29e8149678df786c240d8825"
RERANKER_WEIGHT_SHA256 = "5daeca2481a76b5976a2bdc32f0a78532b6716da4f8cd3ff59460ef8d2f359b4"
REQUIRED_LOCAL_FILES = {
    "config.json",
    "model.safetensors",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
}


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def validated_local_reranker_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    missing = sorted(name for name in REQUIRED_LOCAL_FILES if not (resolved / name).is_file())
    if missing:
        raise FileNotFoundError(f"local reranker snapshot is missing: {', '.join(missing)}")
    if _sha256_file(resolved / "model.safetensors") != RERANKER_WEIGHT_SHA256:
        raise ValueError("local reranker weight checksum does not match the locked revision")
    return resolved


class PairScorer(Protocol):
    def predict(self, pairs: list[tuple[str, str]]) -> Sequence[float]: ...


class CrossEncoderReranker:
    def __init__(self, scorer: PairScorer) -> None:
        self._scorer = scorer

    @classmethod
    def from_pretrained(
        cls,
        model_name: str | Path = DEFAULT_RERANKER,
        revision: str | None = DEFAULT_RERANKER_REVISION,
    ) -> CrossEncoderReranker:
        from sentence_transformers import CrossEncoder

        options = {"revision": revision} if revision is not None else {}
        return cls(CrossEncoder(str(model_name), **options))

    @classmethod
    def from_settings(cls, settings: Settings) -> CrossEncoderReranker:
        if settings.reranker_model_path is None:
            return cls.from_pretrained()
        return cls.from_pretrained(
            validated_local_reranker_path(settings.reranker_model_path),
            revision=None,
        )

    def rerank(
        self,
        query: str,
        candidates: list[SearchResult],
        documents: dict[str, SearchDocument],
        *,
        top_k: int = 10,
    ) -> list[SearchResult]:
        available = [candidate for candidate in candidates if candidate.call_id in documents]
        scores = self._scorer.predict(
            [(query, documents[candidate.call_id].text) for candidate in available]
        )
        ranked = sorted(
            zip(available, scores, strict=True),
            key=lambda item: (-float(item[1]), item[0].call_id),
        )[:top_k]
        return [
            SearchResult(
                call_id=candidate.call_id,
                title=candidate.title,
                programme=candidate.programme,
                official_url=candidate.official_url,
                score=float(score),
                components={**candidate.components, "cross_encoder": float(score)},
            )
            for candidate, score in ranked
        ]
