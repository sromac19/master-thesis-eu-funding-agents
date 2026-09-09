from __future__ import annotations

import operator
from datetime import date
from typing import Annotated, Any, Literal, TypedDict
from urllib.parse import urlparse

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

from eu_funding_agents.eligibility.rule_engine import evaluate_eligibility
from eu_funding_agents.eligibility.schemas import (
    CriterionType,
    ExtractedCriterion,
    OrganisationProfile,
    ProjectProfile,
    RuleOutcome,
    RuleResult,
)
from eu_funding_agents.ranking.multicriteria import CandidateSignals, score_candidate
from eu_funding_agents.retrieval.bm25 import BM25Retriever
from eu_funding_agents.retrieval.types import SearchDocument


class WorkflowCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    programme: str = Field(min_length=1)
    official_url: HttpUrl
    status: Literal["open", "forthcoming", "closed", "unknown"]
    deadline: date | None


class PartnerSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    source_project_id: str = Field(min_length=1)
    source_url: HttpUrl
    explanation: str = Field(min_length=1)


class WorkflowCandidateSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dense: float | None = Field(default=None, ge=0, le=1)
    cross_encoder: float | None = Field(default=None, ge=0, le=1)
    outcome_match: float | None = Field(default=None, ge=0, le=1)
    trl_match: float | None = Field(default=None, ge=0, le=1)
    budget_match: float | None = Field(default=None, ge=0, le=1)
    consortium_readiness: float | None = Field(default=None, ge=0, le=1)
    euroscivoc_match: float | None = Field(default=None, ge=0, le=1)
    historical_similarity: float | None = Field(default=None, ge=0, le=1)
    country_eligible: bool | None = None
    legal_entity_eligible: bool | None = None
    consortium_eligible: bool | None = None


class TraceEvent(TypedDict):
    node: str
    status: str
    detail: str


class ModelUsage(TypedDict):
    provider: str
    model: str
    prompt_version: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float | None


class WorkflowState(TypedDict, total=False):
    as_of: str
    top_k: int
    organisation_input: dict[str, Any]
    project_input: dict[str, Any]
    catalog_input: list[dict[str, Any]]
    candidate_signals_input: dict[str, dict[str, Any]]
    criteria_input: list[dict[str, Any]]
    partner_signals_input: list[dict[str, Any]]
    organisation: dict[str, Any]
    project: dict[str, Any]
    discovered_calls: list[dict[str, Any]]
    retrieval_candidates: list[dict[str, Any]]
    ranked_candidates: list[dict[str, Any]]
    rule_results: list[dict[str, Any]]
    partner_required: bool
    partner_suggestions: list[dict[str, Any]]
    verification_issues: list[str]
    report: dict[str, Any]
    errors: list[str]
    approved: bool
    human_corrections: dict[str, Any]
    trace: Annotated[list[TraceEvent], operator.add]
    model_usage: list[ModelUsage]


WorkflowVariant = Literal[
    "ranking_without_rule_engine",
    "system_without_verifier",
    "full_controlled_system",
]


def profile_node(state: WorkflowState) -> dict[str, Any]:
    try:
        organisation = OrganisationProfile.model_validate(state["organisation_input"])
        project = ProjectProfile.model_validate(state["project_input"])
    except (KeyError, ValidationError) as exc:
        return {
            "errors": [str(exc)],
            "trace": [{"node": "profile", "status": "failed", "detail": "invalid input"}],
        }
    return {
        "organisation": organisation.model_dump(mode="json"),
        "project": project.model_dump(mode="json"),
        "errors": [],
        "trace": [{"node": "profile", "status": "ok", "detail": "profiles validated"}],
    }


def discovery_node(state: WorkflowState) -> dict[str, Any]:
    try:
        as_of = date.fromisoformat(state["as_of"])
        catalog = [WorkflowCall.model_validate(item) for item in state["catalog_input"]]
    except (KeyError, ValueError, ValidationError) as exc:
        return {
            "errors": [*state.get("errors", []), str(exc)],
            "trace": [{"node": "discovery", "status": "failed", "detail": "invalid catalog"}],
        }
    current: dict[str, WorkflowCall] = {}
    for call in catalog:
        if call.status not in {"open", "forthcoming"}:
            continue
        if call.deadline is None or call.deadline < as_of:
            continue
        current.setdefault(call.call_id, call)
    discovered = [current[call_id].model_dump(mode="json") for call_id in sorted(current)]
    return {
        "discovered_calls": discovered,
        "trace": [
            {
                "node": "discovery",
                "status": "ok",
                "detail": f"selected {len(discovered)} confirmed current calls",
            }
        ],
    }


def retrieval_node(state: WorkflowState) -> dict[str, Any]:
    project = ProjectProfile.model_validate(state["project"])
    calls = [WorkflowCall.model_validate(item) for item in state.get("discovered_calls", [])]
    if project.description is None:
        return {
            "errors": [*state.get("errors", []), "project description is required for retrieval"],
            "trace": [{"node": "retrieval", "status": "failed", "detail": "missing query text"}],
        }
    if not calls:
        return {
            "retrieval_candidates": [],
            "trace": [{"node": "retrieval", "status": "ok", "detail": "ranked 0 calls"}],
        }
    documents = [
        SearchDocument(
            call_id=call.call_id,
            title=call.title,
            text="\n".join(part for part in (call.title, call.description) if part),
            programme=call.programme,
            official_url=str(call.official_url),
        )
        for call in calls
    ]
    top_k = min(max(state.get("top_k", 10), 1), 20)
    results = BM25Retriever(documents).search(project.description, top_k=top_k)
    return {
        "retrieval_candidates": [
            {
                "call_id": result.call_id,
                "title": result.title,
                "programme": result.programme,
                "official_url": result.official_url,
                "score": result.score,
                "components": result.components,
            }
            for result in results
        ],
        "trace": [{"node": "retrieval", "status": "ok", "detail": f"ranked {len(results)} calls"}],
    }


def ranking_node(state: WorkflowState) -> dict[str, Any]:
    candidates = state.get("retrieval_candidates", [])
    maximum = max((max(float(item["score"]), 0.0) for item in candidates), default=0.0)
    ranked: list[dict[str, Any]] = []
    try:
        for candidate in candidates:
            call_id = str(candidate["call_id"])
            supplied = WorkflowCandidateSignals.model_validate(
                state.get("candidate_signals_input", {}).get(call_id, {})
            )
            normalized_bm25 = max(float(candidate["score"]), 0.0) / maximum if maximum else 0.0
            result = score_candidate(
                CandidateSignals(
                    call_id=call_id,
                    bm25=normalized_bm25,
                    status_and_deadline_valid=True,
                    **supplied.model_dump(),
                )
            )
            ranked.append(
                {
                    **candidate,
                    "score": result.score,
                    "hard_status": result.hard_status.value,
                    "score_components": result.components,
                    "reasons": list(result.reasons),
                }
            )
    except (TypeError, ValueError, ValidationError) as exc:
        return {
            "errors": [*state.get("errors", []), str(exc)],
            "trace": [{"node": "ranking", "status": "failed", "detail": "invalid ranking signals"}],
        }
    ranked.sort(
        key=lambda item: (
            item["score"] is None,
            -float(item["score"]) if item["score"] is not None else 0.0,
            item["call_id"],
        )
    )
    return {
        "ranked_candidates": ranked,
        "trace": [{"node": "ranking", "status": "ok", "detail": f"scored {len(ranked)} calls"}],
    }


def eligibility_node(state: WorkflowState) -> dict[str, Any]:
    try:
        rules = [ExtractedCriterion.model_validate(item) for item in state["criteria_input"]]
        organisation = OrganisationProfile.model_validate(state["organisation"])
        project = ProjectProfile.model_validate(state["project"])
    except (KeyError, ValidationError) as exc:
        return {
            "errors": [*state.get("errors", []), str(exc)],
            "trace": [{"node": "eligibility", "status": "failed", "detail": "invalid criteria"}],
        }
    results = evaluate_eligibility(rules, organisation, project)
    return {
        "rule_results": [result.model_dump(mode="json") for result in results],
        "trace": [
            {
                "node": "eligibility",
                "status": "ok",
                "detail": f"evaluated {len(results)} criteria",
            }
        ],
    }


def partner_node(state: WorkflowState) -> dict[str, Any]:
    results = [RuleResult.model_validate(item) for item in state.get("rule_results", [])]
    rules = [ExtractedCriterion.model_validate(item) for item in state.get("criteria_input", [])]
    consortium_gap = any(
        rule.criterion is CriterionType.MIN_CONSORTIUM_SIZE
        and rule.applicable is True
        and result.outcome in {RuleOutcome.FAIL, RuleOutcome.UNKNOWN}
        for rule, result in zip(rules, results, strict=True)
    )
    if not consortium_gap:
        return {
            "partner_required": False,
            "partner_suggestions": [],
            "trace": [
                {
                    "node": "partner",
                    "status": "skipped",
                    "detail": "no verified consortium gap",
                }
            ],
        }
    try:
        suggestions = [
            PartnerSuggestion.model_validate(item)
            for item in state.get("partner_signals_input", [])
        ]
    except ValidationError as exc:
        return {
            "errors": [*state.get("errors", []), str(exc)],
            "trace": [{"node": "partner", "status": "failed", "detail": "invalid CORDIS signal"}],
        }
    return {
        "partner_required": True,
        "partner_suggestions": [item.model_dump(mode="json") for item in suggestions],
        "trace": [
            {
                "node": "partner",
                "status": "ok" if suggestions else "requires_verification",
                "detail": f"found {len(suggestions)} historical partner signals",
            }
        ],
    }


def verification_node(state: WorkflowState) -> dict[str, Any]:
    issues: list[str] = []
    if not state.get("ranked_candidates"):
        issues.append("No confirmed active call matched the project profile")
    elif not any(
        candidate["hard_status"] != "fail" for candidate in state.get("ranked_candidates", [])
    ):
        issues.append("All retrieved calls failed at least one hard constraint")
    for candidate in state.get("ranked_candidates", []):
        parsed = urlparse(str(candidate["official_url"]))
        hostname = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or (
            hostname != "europa.eu" and not hostname.endswith(".europa.eu")
        ):
            issues.append(f"Non-official call URL for {candidate['call_id']}")
        if candidate["hard_status"] == "unknown":
            issues.append(f"Unresolved hard constraints for {candidate['call_id']}")
    for raw_result in state.get("rule_results", []):
        result = RuleResult.model_validate(raw_result)
        parsed = urlparse(str(result.source_url))
        hostname = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or (
            hostname != "europa.eu" and not hostname.endswith(".europa.eu")
        ):
            issues.append(f"Non-official evidence host for {result.criterion.value}")
        if result.outcome is RuleOutcome.UNKNOWN:
            issues.append(f"Unresolved criterion: {result.criterion.value}")
        if result.evidence_text is None and result.outcome in {RuleOutcome.PASS, RuleOutcome.FAIL}:
            issues.append(f"Missing evidence for {result.criterion.value}")
    for suggestion in state.get("partner_suggestions", []):
        parsed = urlparse(str(suggestion["source_url"]))
        hostname = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or hostname != "cordis.europa.eu":
            issues.append(f"Non-CORDIS partner source for {suggestion['source_project_id']}")
    if state.get("partner_required") and not state.get("partner_suggestions"):
        issues.append("Verified consortium gap has no historical CORDIS partner signal")
    return {
        "verification_issues": issues,
        "trace": [
            {
                "node": "verification",
                "status": "ok" if not issues else "requires_verification",
                "detail": f"found {len(issues)} issues",
            }
        ],
    }


def report_node(state: WorkflowState) -> dict[str, Any]:
    results = [RuleResult.model_validate(item) for item in state.get("rule_results", [])]
    ranked = state.get("ranked_candidates", [])
    hard_fail = any(result.is_hard and result.outcome is RuleOutcome.FAIL for result in results)
    if state.get("errors"):
        status = "failed"
    elif hard_fail:
        status = "ineligible"
    elif state.get("verification_issues"):
        status = "requires_verification"
    else:
        status = "ready_for_human_review"
    report = {
        "status": status,
        "relevance": [item for item in ranked if item["hard_status"] != "fail"],
        "excluded_candidates": [item for item in ranked if item["hard_status"] == "fail"],
        "eligibility": [result.model_dump(mode="json") for result in results],
        "partners": state.get("partner_suggestions", []),
        "verification_issues": state.get("verification_issues", []),
        "errors": state.get("errors", []),
        "model_usage": state.get("model_usage", []),
        "disclaimer": "Decision support only; this is not legal advice.",
    }
    return {
        "report": report,
        "trace": [{"node": "report", "status": "ok", "detail": f"status={status}"}],
    }


def human_review_node(state: WorkflowState) -> dict[str, Any]:
    decision = interrupt(
        {
            "instruction": "Review the evidence and approve or reject the recommendation.",
            "report": state["report"],
        }
    )
    approved = bool(decision.get("approved")) if isinstance(decision, dict) else False
    corrections = decision.get("corrections", {}) if isinstance(decision, dict) else {}
    report = {**state["report"], "human_review": "approved" if approved else "rejected"}
    return {
        "approved": approved,
        "human_corrections": corrections,
        "report": report,
        "trace": [
            {
                "node": "human_review",
                "status": "approved" if approved else "rejected",
                "detail": "human decision recorded separately",
            }
        ],
    }


def _after_profile(state: WorkflowState) -> Literal["discovery", "report"]:
    return "report" if state.get("errors") else "discovery"


def _after_discovery(state: WorkflowState) -> Literal["retrieval", "report"]:
    return "report" if state.get("errors") else "retrieval"


def _after_retrieval(state: WorkflowState) -> Literal["ranking", "report"]:
    return "report" if state.get("errors") else "ranking"


def _after_ranking(state: WorkflowState) -> Literal["eligibility", "report"]:
    return "report" if state.get("errors") else "eligibility"


def _after_eligibility(state: WorkflowState) -> Literal["partner", "report"]:
    return "report" if state.get("errors") else "partner"


def _after_partner(state: WorkflowState) -> Literal["verification", "report"]:
    return "report" if state.get("errors") else "verification"


def _after_ranking_without_rules(state: WorkflowState) -> Literal["verification", "report"]:
    return "report" if state.get("errors") else "verification"


def _after_partner_without_verifier(state: WorkflowState) -> Literal["report"]:
    return "report"


def build_workflow(
    checkpointer: BaseCheckpointSaver[Any],
    *,
    variant: WorkflowVariant = "full_controlled_system",
) -> Any:
    graph = StateGraph(WorkflowState)
    graph.add_node("profile", profile_node)
    graph.add_node("discovery", discovery_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("ranking", ranking_node)
    if variant != "ranking_without_rule_engine":
        graph.add_node("eligibility", eligibility_node)
        graph.add_node("partner", partner_node)
    if variant != "system_without_verifier":
        graph.add_node("verification", verification_node)
    graph.add_node("report", report_node)
    graph.add_node("human_review", human_review_node)
    graph.add_edge(START, "profile")
    graph.add_conditional_edges("profile", _after_profile)
    graph.add_conditional_edges("discovery", _after_discovery)
    graph.add_conditional_edges("retrieval", _after_retrieval)
    if variant == "ranking_without_rule_engine":
        graph.add_conditional_edges("ranking", _after_ranking_without_rules)
        graph.add_edge("verification", "report")
    else:
        graph.add_conditional_edges("ranking", _after_ranking)
        graph.add_conditional_edges("eligibility", _after_eligibility)
        if variant == "system_without_verifier":
            graph.add_conditional_edges("partner", _after_partner_without_verifier)
        else:
            graph.add_conditional_edges("partner", _after_partner)
            graph.add_edge("verification", "report")
    graph.add_edge("report", "human_review")
    graph.add_edge("human_review", END)
    return graph.compile(checkpointer=checkpointer)
