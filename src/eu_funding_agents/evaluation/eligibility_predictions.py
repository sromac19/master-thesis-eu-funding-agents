from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from eu_funding_agents.eligibility.rule_engine import evaluate_rule
from eu_funding_agents.eligibility.schemas import (
    CriterionType,
    ExtractedCriterion,
    ExtractionStatus,
    OrganisationProfile,
    ProjectProfile,
    RuleOperator,
)


def optional_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized not in {"true", "false"}:
        raise ValueError(f"expected true, false, or empty; got {value!r}")
    return normalized == "true"


def optional_int(value: str) -> int | None:
    return int(value) if value.strip() else None


def expected_value(value: str, operator: RuleOperator) -> str | int | bool | list[str]:
    if operator is RuleOperator.IN:
        parsed = json.loads(value)
        if (
            not isinstance(parsed, list)
            or not parsed
            or not all(isinstance(item, str) and item for item in parsed)
        ):
            raise ValueError("in operator requires a non-empty JSON string list")
        return parsed
    if operator in {RuleOperator.GREATER_THAN_OR_EQUAL, RuleOperator.LESS_THAN_OR_EQUAL}:
        return int(value)
    normalized = value.strip().lower()
    if normalized in {"true", "false"}:
        return normalized == "true"
    if not value.strip():
        raise ValueError("equals operator requires a value")
    return value.strip()


def predict_annotation(row: dict[str, str], profile: dict[str, str]) -> str:
    operator = RuleOperator(row["operator"])
    evidence_supported = optional_bool(row["evidence_supported"])
    if evidence_supported is None:
        raise ValueError("evidence_supported must be verified before prediction")
    rule = ExtractedCriterion(
        criterion=CriterionType(row["criterion_id"]),
        operator=operator,
        expected_value=expected_value(row["expected_value"], operator),
        is_hard=optional_bool(row["is_hard"]),
        applicable=optional_bool(row["applicable"]),
        extraction_status=(
            ExtractionStatus.SUPPORTED if evidence_supported else ExtractionStatus.UNSUPPORTED
        ),
        evidence_text=row["evidence_text"].strip() or None,
        page=optional_int(row["page"]),
        section=row["section"].strip() or None,
        source_url=row["source_url"].strip(),
        confidence=1.0 if evidence_supported else 0.0,
        human_confirmed=True,
    )
    organisation = OrganisationProfile(
        country=profile["country"].strip() or None,
        organisation_type=profile["organisation_type"].strip() or None,
        sme=optional_bool(profile["sme_status"]),
        consortium_size=optional_int(profile["consortium_size"]),
    )
    project = ProjectProfile(trl=optional_int(profile["trl"]))
    return evaluate_rule(rule, organisation, project).outcome.value.upper()


def populate_predictions(
    annotations_path: Path,
    profiles_path: Path,
    output_path: Path,
) -> int:
    with profiles_path.open(encoding="utf-8", newline="") as source:
        profiles = {row["profile_id"]: row for row in csv.DictReader(source)}
    with annotations_path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if not rows or fieldnames is None:
        raise ValueError("eligibility annotation file has no labeled rows")
    if "predicted_status" not in fieldnames:
        raise ValueError("eligibility annotations are missing predicted_status")

    for row_number, row in enumerate(rows, start=2):
        profile_id = row["profile_id"]
        try:
            profile = profiles[profile_id]
            row["predicted_status"] = predict_annotation(row, profile)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"row {row_number}: cannot derive prediction: {exc}") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=output_path.parent,
            suffix=".tmp",
        ) as destination:
            temporary_path = Path(destination.name)
            writer = csv.DictWriter(destination, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return len(rows)
