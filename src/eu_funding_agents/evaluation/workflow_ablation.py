from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from statistics import fmean
from time import perf_counter

from langgraph.checkpoint.memory import InMemorySaver

from eu_funding_agents.agents.workflow import WorkflowVariant, build_workflow

AS_OF = date(2026, 9, 7)
OFFICIAL_URL = "https://ec.europa.eu/info/funding-tenders/opportunities/docs/example.pdf"
VARIANTS: tuple[WorkflowVariant, ...] = (
    "ranking_without_rule_engine",
    "system_without_verifier",
    "full_controlled_system",
)


def _base_input() -> dict[str, object]:
    return {
        "as_of": AS_OF.isoformat(),
        "top_k": 5,
        "organisation_input": {"country": "HR", "consortium_size": 3},
        "project_input": {
            "description": "Renewable energy storage for resilient industrial production.",
            "trl": 5,
        },
        "catalog_input": [
            {
                "call_id": "active-call",
                "title": "Renewable energy storage",
                "description": "Demonstrate storage technology in industry.",
                "programme": "HORIZON",
                "official_url": "https://ec.europa.eu/info/funding-tenders/active-call",
                "status": "open",
                "deadline": (AS_OF + timedelta(days=90)).isoformat(),
            }
        ],
        "candidate_signals_input": {
            "active-call": {
                "dense": 0.8,
                "cross_encoder": 0.9,
                "country_eligible": True,
                "legal_entity_eligible": True,
                "consortium_eligible": True,
            }
        },
        "criteria_input": [
            {
                "criterion": "min_consortium_size",
                "operator": "gte",
                "expected_value": 3,
                "applicable": True,
                "extraction_status": "supported",
                "evidence_text": "At least three independent entities are required.",
                "source_url": OFFICIAL_URL,
                "confidence": 1.0,
            }
        ],
        "trace": [],
        "model_usage": [],
    }


def _scenarios() -> list[tuple[str, dict[str, object], str]]:
    valid = _base_input()
    unknown = deepcopy(valid)
    unknown["criteria_input"][0]["applicable"] = None  # type: ignore[index]
    hard_fail = deepcopy(valid)
    hard_fail["organisation_input"]["consortium_size"] = 1  # type: ignore[index]
    expired = deepcopy(valid)
    expired["catalog_input"][0]["deadline"] = (AS_OF - timedelta(days=1)).isoformat()  # type: ignore[index]
    return [
        ("valid", valid, "ready_for_human_review"),
        ("unknown", unknown, "requires_verification"),
        ("hard_fail", hard_fail, "ineligible"),
        ("expired", expired, "requires_verification"),
    ]


def workflow_ablation_report() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for variant in VARIANTS:
        workflow = build_workflow(InMemorySaver(), variant=variant)
        for scenario, workflow_input, expected_status in _scenarios():
            started = perf_counter()
            result = workflow.invoke(
                workflow_input,
                config={"configurable": {"thread_id": f"{variant}-{scenario}"}},
            )
            latency_ms = (perf_counter() - started) * 1000
            actual_status = str(result["report"]["status"])
            rows.append(
                {
                    "variant": variant,
                    "scenario": scenario,
                    "expected_status": expected_status,
                    "actual_status": actual_status,
                    "correct": actual_status == expected_status,
                    "unsafe_ready": (
                        expected_status != "ready_for_human_review"
                        and actual_status == "ready_for_human_review"
                    ),
                    "schema_valid": isinstance(result["report"], dict)
                    and "disclaimer" in result["report"],
                    "latency_ms": latency_ms,
                }
            )

    metrics: dict[str, dict[str, float]] = {}
    for variant in VARIANTS:
        subset = [row for row in rows if row["variant"] == variant]
        metrics[variant] = {
            "scenario_accuracy": fmean(bool(row["correct"]) for row in subset),
            "unsafe_ready_rate": fmean(bool(row["unsafe_ready"]) for row in subset),
            "schema_success_rate": fmean(bool(row["schema_valid"]) for row in subset),
            "mean_latency_ms": fmean(float(row["latency_ms"]) for row in subset),
        }
    return {
        "benchmark": "controlled_workflow_ablation_v1",
        "scenario_count": len(_scenarios()),
        "by_variant": metrics,
        "runs": rows,
        "limitation": (
            "Controlled deterministic safety scenarios; not human-rated response quality."
        ),
    }
