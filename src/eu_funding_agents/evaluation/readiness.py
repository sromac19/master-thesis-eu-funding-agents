from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

REQUIRED_SECTORS = {
    "digitalisation_industry",
    "energy_environment",
    "health",
    "agriculture_food",
}


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    profile_count: int
    sectors: list[str]
    candidate_counts: dict[str, int]
    repeated_pairs: int
    problems: list[str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TableReadinessReport:
    ready: bool
    row_count: int
    profile_count: int
    pair_count: int
    variants: list[str]
    problems: list[str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def validate_retrieval_annotations(
    path: Path,
    *,
    min_profiles: int = 40,
    min_candidates: int = 10,
    max_candidates: int = 20,
    min_repeat_pairs: int = 40,
) -> ReadinessReport:
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))

    problems: list[str] = []
    required_columns = {
        "profile_id",
        "sector",
        "organisation_type",
        "project_description",
        "call_id",
        "relevance",
        "annotator",
        "annotation_round",
        "notes",
    }
    if not rows:
        return ReadinessReport(False, 0, [], {}, 0, ["annotation file has no labeled rows"])
    missing_columns = required_columns.difference(rows[0])
    if missing_columns:
        return ReadinessReport(
            False,
            0,
            [],
            {},
            0,
            [f"missing columns: {', '.join(sorted(missing_columns))}"],
        )

    profiles: dict[str, set[str]] = defaultdict(set)
    pair_rounds: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    seen_rows: set[tuple[str, str, str, str]] = set()
    annotators: set[str] = set()
    sectors: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        try:
            grade = int(row["relevance"])
        except ValueError:
            problems.append(f"row {row_number}: relevance is not an integer")
            continue
        if grade not in range(4):
            problems.append(f"row {row_number}: relevance must be 0-3")
        annotator = row["annotator"].strip()
        if not annotator:
            problems.append(f"row {row_number}: annotator is empty")
        else:
            annotators.add(annotator)
        annotation_round = row["annotation_round"].strip()
        if annotation_round not in {"initial", "repeat"}:
            problems.append(f"row {row_number}: annotation_round must be initial or repeat")
        profile_id = row["profile_id"].strip()
        call_id = row["call_id"].strip()
        row_key = (profile_id, call_id, annotator, annotation_round)
        if row_key in seen_rows:
            problems.append(f"row {row_number}: duplicate annotation round")
        seen_rows.add(row_key)
        pair_rounds[(profile_id, call_id, annotator)].add(annotation_round)
        if annotation_round == "initial":
            profiles[profile_id].add(call_id)
            sectors.add(row["sector"].strip())

    candidate_counts = {key: len(value) for key, value in sorted(profiles.items())}
    if len(profiles) < min_profiles:
        problems.append(f"need at least {min_profiles} profiles; found {len(profiles)}")
    missing_sectors = REQUIRED_SECTORS.difference(sectors)
    if missing_sectors:
        problems.append(f"missing sectors: {', '.join(sorted(missing_sectors))}")
    for profile_id, count in candidate_counts.items():
        if not min_candidates <= count <= max_candidates:
            problems.append(
                f"profile {profile_id}: candidate count {count} is outside "
                f"{min_candidates}-{max_candidates}"
            )
    if len(annotators) != 1:
        problems.append(f"solo protocol requires exactly one annotator; found {len(annotators)}")
    repeated_pairs = sum(rounds == {"initial", "repeat"} for rounds in pair_rounds.values())
    orphan_repeats = sum(
        "repeat" in rounds and "initial" not in rounds for rounds in pair_rounds.values()
    )
    if orphan_repeats:
        problems.append(f"repeat annotations without an initial label: {orphan_repeats}")
    if repeated_pairs < min_repeat_pairs:
        problems.append(
            f"need at least {min_repeat_pairs} blinded repeat pairs; found {repeated_pairs}"
        )

    return ReadinessReport(
        ready=not problems,
        profile_count=len(profiles),
        sectors=sorted(sectors),
        candidate_counts=candidate_counts,
        repeated_pairs=repeated_pairs,
        problems=problems,
    )


def validate_eligibility_annotations(path: Path) -> TableReadinessReport:
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        return TableReadinessReport(False, 0, 0, 0, [], ["annotation file has no labeled rows"])

    required = {
        "profile_id",
        "call_id",
        "criterion_id",
        "operator",
        "expected_value",
        "is_hard",
        "applicable",
        "expected_status",
        "predicted_status",
        "status_deadline_correct",
        "evidence_supported",
        "evidence_text",
        "source_url",
        "page",
        "section",
        "annotator",
        "notes",
    }
    missing = required.difference(rows[0])
    if missing:
        return TableReadinessReport(
            False, len(rows), 0, 0, [], [f"missing columns: {', '.join(sorted(missing))}"]
        )

    problems: list[str] = []
    labels = {"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}
    criteria = {
        "country_allowed",
        "organisation_type_allowed",
        "sme_required",
        "min_consortium_size",
        "min_trl",
        "max_trl",
    }
    operators = {"in", "equals", "gte", "lte"}
    criterion_operators = {
        "country_allowed": "in",
        "organisation_type_allowed": "in",
        "sme_required": "equals",
        "min_consortium_size": "gte",
        "min_trl": "gte",
        "max_trl": "lte",
    }
    profile_calls: dict[str, set[str]] = defaultdict(set)
    for row_number, row in enumerate(rows, start=2):
        profile_calls[row["profile_id"]].add(row["call_id"])
        if row["criterion_id"] not in criteria:
            problems.append(f"row {row_number}: invalid criterion_id")
        if row["operator"] not in operators:
            problems.append(f"row {row_number}: invalid operator")
        elif (
            row["criterion_id"] in criterion_operators
            and row["operator"] != criterion_operators[row["criterion_id"]]
        ):
            problems.append(f"row {row_number}: operator does not match criterion")
        try:
            if row["operator"] == "in":
                expected = json.loads(row["expected_value"])
                if (
                    not isinstance(expected, list)
                    or not expected
                    or not all(isinstance(item, str) and item for item in expected)
                ):
                    raise ValueError
            elif row["operator"] in {"gte", "lte"}:
                int(row["expected_value"])
            elif row["operator"] == "equals" and not row["expected_value"].strip():
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            problems.append(f"row {row_number}: expected_value does not match operator")
        if row["expected_status"] not in labels:
            problems.append(f"row {row_number}: invalid expected_status")
        if row["predicted_status"] not in labels:
            problems.append(f"row {row_number}: predicted_status is missing or invalid")
        for field in ("is_hard", "applicable", "status_deadline_correct", "evidence_supported"):
            if row[field].strip().lower() not in {"", "true", "false"}:
                problems.append(f"row {row_number}: invalid {field}")
        for field in ("is_hard", "status_deadline_correct", "evidence_supported"):
            if not row[field].strip():
                problems.append(f"row {row_number}: {field} is required for final evaluation")
        if row["evidence_supported"].strip().lower() == "true" and not (
            row["evidence_text"].strip() and row["source_url"].strip()
        ):
            problems.append(
                f"row {row_number}: supported evidence requires evidence_text and source_url"
            )
        parsed_url = urlparse(row["source_url"])
        hostname = (parsed_url.hostname or "").lower()
        if parsed_url.scheme != "https" or not (
            hostname == "europa.eu" or hostname.endswith(".europa.eu")
        ):
            problems.append(f"row {row_number}: criterion source URL is not official")
        if row["page"].strip():
            try:
                if int(row["page"]) < 1:
                    raise ValueError
            except ValueError:
                problems.append(f"row {row_number}: page must be a positive integer or empty")
    pair_count = sum(len(calls) for calls in profile_calls.values())
    if len(profile_calls) < 20:
        problems.append(f"need at least 20 profiles; found {len(profile_calls)}")
    if not 60 <= pair_count <= 90:
        problems.append(f"need 60-90 unique profile-call pairs; found {pair_count}")
    for profile_id, calls in sorted(profile_calls.items()):
        if len(calls) != 3:
            problems.append(f"profile {profile_id}: expected 3 calls; found {len(calls)}")
    return TableReadinessReport(
        not problems, len(rows), len(profile_calls), pair_count, [], problems
    )


def validate_agent_annotations(path: Path) -> TableReadinessReport:
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        return TableReadinessReport(False, 0, 0, 0, [], ["annotation file has no runs"])
    required = {
        "run_id",
        "variant",
        "provider",
        "model",
        "prompt_version",
        "snapshot_id",
        "citation_supported",
        "claim_faithful",
        "unknown_correct",
        "schema_valid",
        "tool_calls",
        "tool_call_failures",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "estimated_cost_eur",
        "human_corrections",
        "notes",
    }
    missing = required.difference(rows[0])
    variants = sorted({row.get("variant", "") for row in rows})
    problems = [f"missing columns: {', '.join(sorted(missing))}"] if missing else []
    expected_variants = {
        "ranking_without_rule_engine",
        "system_without_verifier",
        "full_controlled_system",
    }
    absent = expected_variants.difference(variants)
    if absent:
        problems.append(f"missing system variants: {', '.join(sorted(absent))}")
    if not missing:
        for row_number, row in enumerate(rows, start=2):
            for field in ("provider", "model", "prompt_version", "snapshot_id"):
                if not row[field].strip():
                    problems.append(f"row {row_number}: {field} is empty")
            for field in (
                "citation_supported",
                "claim_faithful",
                "unknown_correct",
                "schema_valid",
            ):
                if row[field].strip().lower() not in {"true", "false"}:
                    problems.append(f"row {row_number}: invalid {field}")
            try:
                tool_calls = int(row["tool_calls"])
                tool_failures = int(row["tool_call_failures"])
                integer_values = (
                    tool_calls,
                    tool_failures,
                    int(row["input_tokens"]),
                    int(row["output_tokens"]),
                    int(row["human_corrections"]),
                )
                decimal_values = (float(row["latency_ms"]), float(row["estimated_cost_eur"]))
                if any(value < 0 for value in (*integer_values, *decimal_values)):
                    raise ValueError
                if tool_failures > tool_calls:
                    problems.append(f"row {row_number}: tool failures exceed tool calls")
            except ValueError:
                problems.append(f"row {row_number}: numeric metrics must be non-negative")
    return TableReadinessReport(not problems, len(rows), 0, 0, variants, problems)


def validate_experiment_config(path: Path) -> list[str]:
    config = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    required_retrieval = {"bm25", "dense", "hybrid", "hybrid_cross_encoder"}
    required_system = {
        "ranking_without_rule_engine",
        "system_without_verifier",
        "full_controlled_system",
    }
    if set(config.get("retrieval_methods", [])) != required_retrieval:
        problems.append("retrieval method set is incomplete")
    if set(config.get("system_ablations", [])) != required_system:
        problems.append("system ablation set is incomplete")
    if config.get("split") not in {"call-disjoint", "temporal"}:
        problems.append("split must be call-disjoint or temporal")
    if not config.get("weights_locked_before_test"):
        problems.append("weights are not locked before test evaluation")
    if not config.get("gold_set_frozen"):
        problems.append("gold set is not frozen")
    protocol = config.get("annotation_protocol")
    solo_protocol = isinstance(protocol, dict) and (
        protocol.get("design") == "single_annotator_test_retest"
        and protocol.get("primary_round") == "initial"
        and protocol.get("repeat_round") == "repeat"
        and protocol.get("repeat_pairs") == 40
    )
    assisted_protocol = isinstance(protocol, dict) and (
        protocol.get("design") == "llm_silver_with_cordis_linkage_benchmark"
        and protocol.get("human_pilot_is_gold") is False
        and protocol.get("llm_labels_are_gold") is False
        and protocol.get("cordis_split") == "project-disjoint"
    )
    if not solo_protocol and not assisted_protocol:
        problems.append("evaluation annotation protocol is not locked")
    llm = config.get("llm")
    if not isinstance(llm, dict) or not all(
        llm.get(field) for field in ("provider", "model", "prompt_version")
    ):
        problems.append("LLM provider, model, and prompt version are not locked")
    return problems
