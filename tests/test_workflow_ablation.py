from eu_funding_agents.evaluation.workflow_ablation import workflow_ablation_report


def test_full_workflow_is_safer_than_controlled_ablations() -> None:
    report = workflow_ablation_report()
    metrics = report["by_variant"]

    assert report["scenario_count"] == 4
    assert metrics["full_controlled_system"]["scenario_accuracy"] == 1.0
    assert metrics["full_controlled_system"]["unsafe_ready_rate"] == 0.0
    assert metrics["full_controlled_system"]["schema_success_rate"] == 1.0
    assert metrics["system_without_verifier"]["scenario_accuracy"] < 1.0
    assert metrics["ranking_without_rule_engine"]["scenario_accuracy"] < 1.0
