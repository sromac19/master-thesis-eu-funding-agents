from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from eu_funding_agents.evaluation.reporting import RETRIEVAL_METHODS, RETRIEVAL_METRICS, _bar_chart


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"report must be a JSON object: {path}")
    return value


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def generate_assisted_report(results_dir: Path, output_dir: Path) -> list[Path]:
    retrieval = {
        method: _load(results_dir / f"silver-{method.replace('_', '-')}-open.json")
        for method in RETRIEVAL_METHODS
    }
    cordis = {
        method: _load(results_dir / f"cordis_topic_retrieval_{method}_v2.json")
        for method in ("bm25", "dense", "hybrid")
    }
    eligibility = _load(results_dir / "synthetic-eligibility.json")
    workflow = _load(results_dir / "workflow-ablation.json")

    annotation_hashes = {str(report.get("annotation_sha256")) for report in retrieval.values()}
    corpus_hashes = {str(report.get("corpus_sha256")) for report in retrieval.values()}
    scopes = {str(report.get("evaluation_scope")) for report in retrieval.values()}
    if (
        len(annotation_hashes) != 1
        or len(corpus_hashes) != 1
        or scopes != {"open_corpus_unjudged_as_nonrelevant"}
    ):
        raise ValueError("retrieval reports are not directly comparable")

    retrieval_rows = [
        {"method": method, **{metric: report["overall"][metric] for metric in RETRIEVAL_METRICS}}
        for method, report in retrieval.items()
    ]
    cordis_rows = [{"method": method, **report["metrics"]} for method, report in cordis.items()]
    eligibility_metrics = eligibility["metrics"]
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = [
        output_dir / "retrieval-silver-overall.csv",
        output_dir / "cordis-project-topic.csv",
        output_dir / "synthetic-eligibility.csv",
        output_dir / "retrieval-silver-overall.png",
        output_dir / "workflow-ablation.csv",
        output_dir / "workflow-ablation.png",
        output_dir / "summary.md",
    ]
    _write_csv(artifacts[0], ["method", *RETRIEVAL_METRICS], retrieval_rows)
    _write_csv(
        artifacts[1],
        ["method", "hit_rate_at_1", "hit_rate_at_5", "hit_rate_at_10", "mrr_at_100"],
        cordis_rows,
    )
    _write_csv(
        artifacts[2],
        ["metric", "value"],
        [{"metric": key, "value": value} for key, value in eligibility_metrics.items()],
    )
    _bar_chart(
        artifacts[3],
        title="Retrieval on current-call LLM silver labels",
        categories=["BM25", "Dense", "Hybrid", "Hybrid + cross-encoder"],
        series={
            label: [float(row[metric]) for row in retrieval_rows]
            for label, metric in (
                ("Recall@10", "recall_at_10"),
                ("Precision@5", "precision_at_5"),
                ("MRR", "mrr"),
                ("nDCG@10", "ndcg_at_10"),
            )
        },
        ylabel="score",
    )
    workflow_rows = [
        {"variant": variant, **metrics} for variant, metrics in workflow["by_variant"].items()
    ]
    _write_csv(
        artifacts[4],
        [
            "variant",
            "scenario_accuracy",
            "unsafe_ready_rate",
            "schema_success_rate",
            "mean_latency_ms",
        ],
        workflow_rows,
    )
    _bar_chart(
        artifacts[5],
        title="Controlled workflow safety ablation",
        categories=["Without rule engine", "Without verifier", "Full controlled system"],
        series={
            label: [float(row[metric]) for row in workflow_rows]
            for label, metric in (
                ("Scenario accuracy", "scenario_accuracy"),
                ("Unsafe-ready rate", "unsafe_ready_rate"),
                ("Schema success", "schema_success_rate"),
            )
        },
        ylabel="rate",
    )

    best = {
        metric: max(retrieval_rows, key=lambda row: float(row[metric]))
        for metric in RETRIEVAL_METRICS
    }
    baseline_ndcg = float(retrieval["bm25"]["overall"]["ndcg_at_10"])
    dense_ndcg = float(retrieval["dense"]["overall"]["ndcg_at_10"])
    relative_ndcg = (dense_ndcg - baseline_ndcg) / baseline_ndcg
    full_workflow = workflow["by_variant"]["full_controlled_system"]
    artifacts[6].write_text(
        "# Assisted evaluation summary\n\n"
        "## Current-call retrieval (LLM silver, 40 profiles)\n\n"
        f"- Best Recall@10: **{best['recall_at_10']['method']}** "
        f"({float(best['recall_at_10']['recall_at_10']):.3f}).\n"
        f"- Best Precision@5: **{best['precision_at_5']['method']}** "
        f"({float(best['precision_at_5']['precision_at_5']):.3f}).\n"
        f"- Best MRR: **{best['mrr']['method']}** ({float(best['mrr']['mrr']):.3f}).\n"
        f"- Best nDCG@10: **{best['ndcg_at_10']['method']}** "
        f"({float(best['ndcg_at_10']['ndcg_at_10']):.3f}).\n"
        f"- Dense nDCG@10 relative improvement over BM25: **{relative_ndcg:.1%}**.\n\n"
        "These relevance labels are an LLM silver standard, not expert human gold. "
        "Unjudged calls are conservatively treated as non-relevant.\n\n"
        "## CORDIS project-topic benchmark\n\n"
        "The benchmark uses a project-disjoint split and actual administrative "
        "project-topic links. It measures historical linked-topic retrieval, not legal "
        "eligibility or current-call relevance grades.\n\n"
        "## Synthetic eligibility safety\n\n"
        f"- Macro-F1: **{float(eligibility_metrics['macro_f1']):.3f}**.\n"
        f"- False-eligible rate: **{float(eligibility_metrics['false_eligible_rate']):.3f}**.\n"
        f"- UNKNOWN accuracy: **{float(eligibility_metrics['unknown_accuracy']):.3f}**.\n\n"
        "Eligibility values come from controlled synthetic rule cases and demonstrate "
        "deterministic engine behavior, not expert legal validation on real calls.\n\n"
        "## Controlled workflow ablation\n\n"
        f"- Full-system scenario accuracy: **{float(full_workflow['scenario_accuracy']):.3f}**.\n"
        f"- Full-system unsafe-ready rate: **{float(full_workflow['unsafe_ready_rate']):.3f}**.\n"
        f"- Full-system schema success: **{float(full_workflow['schema_success_rate']):.3f}**.\n\n"
        "The ablation uses controlled deterministic safety scenarios, not human-rated "
        "response quality.\n",
        encoding="utf-8",
    )
    return artifacts
