from eu_funding_agents.evaluation.synthetic_eligibility import synthetic_eligibility_report


def test_synthetic_eligibility_covers_all_outcomes_without_false_eligible_cases() -> None:
    report = synthetic_eligibility_report()

    assert report["case_count"] == 24
    assert report["criterion_count"] == 6
    metrics = report["metrics"]
    assert metrics["macro_f1"] == 1.0
    assert metrics["false_eligible_rate"] == 0.0
    assert metrics["unknown_accuracy"] == 1.0
    assert metrics["evidence_coverage"] == 1.0
