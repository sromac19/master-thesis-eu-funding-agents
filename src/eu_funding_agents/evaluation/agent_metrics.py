from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean


@dataclass(frozen=True)
class AgentObservation:
    citation_supported: bool
    claim_faithful: bool
    unknown_correct: bool
    schema_valid: bool
    tool_calls: int
    tool_call_failures: int
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_eur: float
    human_corrections: int


def aggregate_agent_metrics(observations: list[AgentObservation]) -> dict[str, float]:
    if not observations:
        raise ValueError("at least one agent observation is required")
    total_calls = sum(item.tool_calls for item in observations)
    total_failures = sum(item.tool_call_failures for item in observations)
    return {
        "citation_precision": fmean(item.citation_supported for item in observations),
        "claim_faithfulness": fmean(item.claim_faithful for item in observations),
        "unsupported_claim_rate": fmean(not item.claim_faithful for item in observations),
        "unknown_accuracy": fmean(item.unknown_correct for item in observations),
        "schema_validation_success_rate": fmean(item.schema_valid for item in observations),
        "tool_call_success_rate": (
            (total_calls - total_failures) / total_calls if total_calls else 1.0
        ),
        "mean_latency_ms": fmean(item.latency_ms for item in observations),
        "mean_input_tokens": fmean(item.input_tokens for item in observations),
        "mean_output_tokens": fmean(item.output_tokens for item in observations),
        "mean_estimated_cost_eur": fmean(item.estimated_cost_eur for item in observations),
        "mean_human_corrections": fmean(item.human_corrections for item in observations),
    }
