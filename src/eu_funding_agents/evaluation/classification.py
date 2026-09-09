from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EvaluationLabel(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class EligibilityObservation:
    expected: EvaluationLabel
    predicted: EvaluationLabel
    status_deadline_correct: bool | None = None
    evidence_supported: bool | None = None


@dataclass(frozen=True)
class EligibilityMetrics:
    precision: float
    recall: float
    macro_f1: float
    false_eligible_rate: float
    unknown_accuracy: float
    status_deadline_accuracy: float | None
    evidence_coverage: float | None


def _safe_divide(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def eligibility_metrics(observations: list[EligibilityObservation]) -> EligibilityMetrics:
    if not observations:
        raise ValueError("at least one eligibility observation is required")

    precisions: list[float] = []
    recalls: list[float] = []
    f1_scores: list[float] = []
    for label in EvaluationLabel:
        true_positive = sum(
            item.expected == label and item.predicted == label for item in observations
        )
        predicted_positive = sum(item.predicted == label for item in observations)
        actual_positive = sum(item.expected == label for item in observations)
        precision = _safe_divide(true_positive, predicted_positive)
        recall = _safe_divide(true_positive, actual_positive)
        precisions.append(precision)
        recalls.append(recall)
        f1_scores.append(
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )

    non_pass = [item for item in observations if item.expected != EvaluationLabel.PASS]
    unknown = [item for item in observations if item.expected == EvaluationLabel.UNKNOWN]
    status_deadline = [
        item.status_deadline_correct
        for item in observations
        if item.status_deadline_correct is not None
    ]
    evidence = [
        item.evidence_supported for item in observations if item.evidence_supported is not None
    ]
    return EligibilityMetrics(
        precision=sum(precisions) / len(precisions),
        recall=sum(recalls) / len(recalls),
        macro_f1=sum(f1_scores) / len(f1_scores),
        false_eligible_rate=_safe_divide(
            sum(item.predicted == EvaluationLabel.PASS for item in non_pass), len(non_pass)
        ),
        unknown_accuracy=_safe_divide(
            sum(item.predicted == EvaluationLabel.UNKNOWN for item in unknown), len(unknown)
        ),
        status_deadline_accuracy=(
            sum(status_deadline) / len(status_deadline) if status_deadline else None
        ),
        evidence_coverage=sum(evidence) / len(evidence) if evidence else None,
    )
