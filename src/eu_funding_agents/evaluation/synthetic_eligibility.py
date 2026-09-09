from __future__ import annotations

from dataclasses import asdict

from eu_funding_agents.eligibility.rule_engine import evaluate_rule
from eu_funding_agents.eligibility.schemas import (
    CriterionType,
    ExtractedCriterion,
    ExtractionStatus,
    OrganisationProfile,
    ProjectProfile,
    RuleOperator,
)
from eu_funding_agents.evaluation.classification import (
    EligibilityObservation,
    EvaluationLabel,
    eligibility_metrics,
)

SOURCE_URL = "https://ec.europa.eu/info/funding-tenders/opportunities/docs/example.pdf"


def _rule(
    criterion: CriterionType,
    operator: RuleOperator,
    expected_value: str | int | bool | list[str],
    *,
    applicable: bool | None = True,
) -> ExtractedCriterion:
    return ExtractedCriterion(
        criterion=criterion,
        operator=operator,
        expected_value=expected_value,
        applicable=applicable,
        extraction_status=ExtractionStatus.SUPPORTED,
        evidence_text="Controlled benchmark evidence.",
        source_url=SOURCE_URL,
        confidence=1.0,
    )


def synthetic_eligibility_report() -> dict[str, object]:
    definitions = [
        (
            CriterionType.COUNTRY_ALLOWED,
            RuleOperator.IN,
            ["HR", "DE"],
            OrganisationProfile(country="HR"),
            OrganisationProfile(country="US"),
            OrganisationProfile(country=None),
            ProjectProfile(),
        ),
        (
            CriterionType.ORGANISATION_TYPE_ALLOWED,
            RuleOperator.IN,
            ["SME", "university"],
            OrganisationProfile(organisation_type="SME"),
            OrganisationProfile(organisation_type="public_body"),
            OrganisationProfile(organisation_type=None),
            ProjectProfile(),
        ),
        (
            CriterionType.SME_REQUIRED,
            RuleOperator.EQUALS,
            True,
            OrganisationProfile(sme=True),
            OrganisationProfile(sme=False),
            OrganisationProfile(sme=None),
            ProjectProfile(),
        ),
        (
            CriterionType.MIN_CONSORTIUM_SIZE,
            RuleOperator.GREATER_THAN_OR_EQUAL,
            3,
            OrganisationProfile(consortium_size=3),
            OrganisationProfile(consortium_size=2),
            OrganisationProfile(consortium_size=None),
            ProjectProfile(),
        ),
        (
            CriterionType.MIN_TRL,
            RuleOperator.GREATER_THAN_OR_EQUAL,
            5,
            OrganisationProfile(),
            OrganisationProfile(),
            OrganisationProfile(),
            ProjectProfile(trl=6),
        ),
        (
            CriterionType.MAX_TRL,
            RuleOperator.LESS_THAN_OR_EQUAL,
            7,
            OrganisationProfile(),
            OrganisationProfile(),
            OrganisationProfile(),
            ProjectProfile(trl=6),
        ),
    ]
    observations: list[EligibilityObservation] = []
    cases: list[dict[str, str]] = []
    for (
        criterion,
        operator,
        expected,
        passing_org,
        failing_org,
        unknown_org,
        project,
    ) in definitions:
        profiles = (
            (EvaluationLabel.PASS, passing_org, project),
            (
                EvaluationLabel.FAIL,
                failing_org,
                ProjectProfile(trl=4)
                if criterion is CriterionType.MIN_TRL
                else ProjectProfile(trl=8)
                if criterion is CriterionType.MAX_TRL
                else project,
            ),
            (
                EvaluationLabel.UNKNOWN,
                unknown_org,
                ProjectProfile()
                if criterion in {CriterionType.MIN_TRL, CriterionType.MAX_TRL}
                else project,
            ),
        )
        for expected_label, organisation, case_project in profiles:
            result = evaluate_rule(_rule(criterion, operator, expected), organisation, case_project)
            predicted = EvaluationLabel(result.outcome.value.upper())
            observations.append(
                EligibilityObservation(
                    expected=expected_label,
                    predicted=predicted,
                    evidence_supported=bool(result.evidence_text),
                )
            )
            cases.append(
                {
                    "criterion": criterion.value,
                    "expected": expected_label.value,
                    "predicted": predicted.value,
                }
            )
        not_applicable = evaluate_rule(
            _rule(criterion, operator, expected, applicable=False), passing_org, project
        )
        predicted = EvaluationLabel(not_applicable.outcome.value.upper())
        observations.append(
            EligibilityObservation(
                expected=EvaluationLabel.NOT_APPLICABLE,
                predicted=predicted,
                evidence_supported=bool(not_applicable.evidence_text),
            )
        )
        cases.append(
            {
                "criterion": criterion.value,
                "expected": EvaluationLabel.NOT_APPLICABLE.value,
                "predicted": predicted.value,
            }
        )

    return {
        "benchmark": "controlled_synthetic_rule_cases_v1",
        "case_count": len(cases),
        "criterion_count": len(definitions),
        "metrics": asdict(eligibility_metrics(observations)),
        "cases": cases,
        "limitation": (
            "Deterministic synthetic rule coverage; not empirical legal eligibility accuracy "
            "on expert-annotated funding calls."
        ),
    }
