from __future__ import annotations

from eu_funding_agents.eligibility.schemas import (
    CriterionType,
    ExtractedCriterion,
    ExtractionStatus,
    OrganisationProfile,
    ProjectProfile,
    RuleOperator,
    RuleOutcome,
    RuleResult,
)


def _actual_value(
    rule: ExtractedCriterion,
    organisation: OrganisationProfile,
    project: ProjectProfile,
) -> str | int | bool | None:
    mapping: dict[CriterionType, str | int | bool | None] = {
        CriterionType.COUNTRY_ALLOWED: organisation.country,
        CriterionType.ORGANISATION_TYPE_ALLOWED: organisation.organisation_type,
        CriterionType.SME_REQUIRED: organisation.sme,
        CriterionType.MIN_CONSORTIUM_SIZE: organisation.consortium_size,
        CriterionType.MIN_TRL: project.trl,
        CriterionType.MAX_TRL: project.trl,
    }
    return mapping[rule.criterion]


def _matches(rule: ExtractedCriterion, actual: str | int | bool) -> bool:
    expected = rule.expected_value
    if rule.operator is RuleOperator.IN:
        return isinstance(expected, list) and str(actual).casefold() in {
            item.casefold() for item in expected
        }
    if rule.operator is RuleOperator.EQUALS:
        if isinstance(actual, str) and isinstance(expected, str):
            return actual.casefold() == expected.casefold()
        return actual == expected
    if rule.operator is RuleOperator.GREATER_THAN_OR_EQUAL:
        return isinstance(actual, int) and isinstance(expected, int) and actual >= expected
    if rule.operator is RuleOperator.LESS_THAN_OR_EQUAL:
        return isinstance(actual, int) and isinstance(expected, int) and actual <= expected
    return False


def evaluate_rule(
    rule: ExtractedCriterion,
    organisation: OrganisationProfile,
    project: ProjectProfile,
) -> RuleResult:
    actual = _actual_value(rule, organisation, project)
    if rule.applicable is False:
        outcome = RuleOutcome.NOT_APPLICABLE
        reason = "Criterion is explicitly marked as not applicable"
    elif rule.applicable is None:
        outcome = RuleOutcome.UNKNOWN
        reason = "Applicability to the specific call has not been verified"
    elif rule.extraction_status is ExtractionStatus.UNSUPPORTED or rule.expected_value is None:
        outcome = RuleOutcome.UNKNOWN
        reason = "The document does not provide supported structured evidence"
    elif actual is None:
        outcome = RuleOutcome.UNKNOWN
        reason = "The applicant or project profile is missing the required value"
    elif _matches(rule, actual):
        outcome = RuleOutcome.PASS
        reason = "The supplied profile value satisfies the supported criterion"
    else:
        outcome = RuleOutcome.FAIL
        reason = "The supplied profile value conflicts with the supported criterion"
    return RuleResult(
        criterion=rule.criterion,
        outcome=outcome,
        is_hard=rule.is_hard,
        actual_value=actual,
        expected_value=rule.expected_value,
        reason=reason,
        evidence_text=rule.evidence_text,
        source_url=rule.source_url,
    )


def evaluate_eligibility(
    rules: list[ExtractedCriterion],
    organisation: OrganisationProfile,
    project: ProjectProfile,
) -> list[RuleResult]:
    return [evaluate_rule(rule, organisation, project) for rule in rules]
