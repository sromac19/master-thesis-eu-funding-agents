from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HardConstraintStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CandidateSignals:
    call_id: str
    bm25: float | None = None
    dense: float | None = None
    cross_encoder: float | None = None
    outcome_match: float | None = None
    trl_match: float | None = None
    budget_match: float | None = None
    consortium_readiness: float | None = None
    euroscivoc_match: float | None = None
    historical_similarity: float | None = None
    status_and_deadline_valid: bool | None = None
    country_eligible: bool | None = None
    legal_entity_eligible: bool | None = None
    consortium_eligible: bool | None = None


@dataclass(frozen=True)
class RankedCandidate:
    call_id: str
    hard_status: HardConstraintStatus
    score: float | None
    components: dict[str, float | None]
    reasons: tuple[str, ...]


DEFAULT_WEIGHTS = {
    "bm25": 0.15,
    "dense": 0.20,
    "cross_encoder": 0.30,
    "outcome_match": 0.10,
    "trl_match": 0.05,
    "budget_match": 0.05,
    "consortium_readiness": 0.05,
    "euroscivoc_match": 0.05,
    "historical_similarity": 0.05,
}


def score_candidate(
    signals: CandidateSignals, weights: dict[str, float] | None = None
) -> RankedCandidate:
    selected_weights = weights or DEFAULT_WEIGHTS
    if set(selected_weights) != set(DEFAULT_WEIGHTS) or any(
        weight < 0 for weight in selected_weights.values()
    ):
        raise ValueError("weights must contain every supported non-negative component")
    hard = {
        "status_and_deadline": signals.status_and_deadline_valid,
        "country": signals.country_eligible,
        "legal_entity": signals.legal_entity_eligible,
        "consortium": signals.consortium_eligible,
    }
    failed = [name for name, value in hard.items() if value is False]
    unknown = [name for name, value in hard.items() if value is None]
    components = {name: getattr(signals, name) for name in DEFAULT_WEIGHTS}
    if any(value is not None and not 0 <= value <= 1 for value in components.values()):
        raise ValueError("soft signals must be normalized to the [0, 1] range")
    if failed:
        return RankedCandidate(
            signals.call_id,
            HardConstraintStatus.FAIL,
            None,
            components,
            tuple(f"Hard constraint failed: {name}" for name in failed),
        )
    known = {name: value for name, value in components.items() if value is not None}
    denominator = sum(selected_weights[name] for name in known)
    if denominator == 0:
        raise ValueError("at least one known soft signal must have a positive weight")
    score = (
        sum(selected_weights[name] * float(value) for name, value in known.items()) / denominator
    )
    reasons = tuple(f"Unknown hard constraint: {name}" for name in unknown)
    return RankedCandidate(
        call_id=signals.call_id,
        hard_status=HardConstraintStatus.UNKNOWN if unknown else HardConstraintStatus.PASS,
        score=score,
        components=components,
        reasons=reasons,
    )
