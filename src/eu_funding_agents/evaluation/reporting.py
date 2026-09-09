from __future__ import annotations

import csv
import json
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

RETRIEVAL_METHODS = ("bm25", "dense", "hybrid", "hybrid_cross_encoder")
RETRIEVAL_METRICS = (
    "recall_at_5",
    "recall_at_10",
    "precision_at_5",
    "mrr",
    "ndcg_at_5",
    "ndcg_at_10",
)


class EvaluationReportError(ValueError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationReportError(f"Cannot read evaluation result: {path}") from exc
    if not isinstance(value, dict):
        raise EvaluationReportError(f"Evaluation result must be an object: {path}")
    return value


def _number(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationReportError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise EvaluationReportError(f"{label} must be finite")
    return number


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _bar_chart(
    path: Path,
    *,
    title: str,
    categories: list[str],
    series: dict[str, list[float]],
    ylabel: str,
) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
    except ImportError as exc:
        raise EvaluationReportError(
            'Install reporting dependencies with pip install -e ".[ml]"'
        ) from exc

    width = 0.8 / max(len(series), 1)
    positions = list(range(len(categories)))
    figure, axis = plt.subplots(figsize=(max(8, len(categories) * 1.3), 5))
    for index, (name, values) in enumerate(series.items()):
        offset = (index - (len(series) - 1) / 2) * width
        axis.bar([position + offset for position in positions], values, width=width, label=name)
    axis.set_title(title)
    axis.set_ylabel(ylabel)
    axis.set_xticks(positions, categories, rotation=20, ha="right")
    axis.grid(axis="y", alpha=0.25)
    if len(series) > 1:
        axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _operation_chart(path: Path, rows: list[dict[str, object]]) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
    except ImportError as exc:
        raise EvaluationReportError(
            'Install reporting dependencies with pip install -e ".[ml]"'
        ) from exc

    variants = [str(row["variant"]) for row in rows]
    panels = (
        ("mean_latency_ms", "Latency", "ms"),
        ("mean_estimated_cost_eur", "Estimated cost", "EUR"),
        ("mean_human_corrections", "Human corrections", "count"),
    )
    figure, axes = plt.subplots(1, len(panels), figsize=(15, 5))
    for axis, (metric, title, ylabel) in zip(axes, panels, strict=True):
        axis.bar(variants, [float(row[metric]) for row in rows])
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.tick_params(axis="x", rotation=20)
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle("Controlled-system operational metrics")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def generate_evaluation_report(results_dir: Path, output_dir: Path) -> list[Path]:
    retrieval = {
        method: _load_object(results_dir / f"retrieval-{method}.json")
        for method in RETRIEVAL_METHODS
    }
    eligibility = _load_object(results_dir / "eligibility.json")
    agents = _load_object(results_dir / "agents.json")
    run_manifest = _load_object(results_dir / "run-manifest.json")
    output_dir.mkdir(parents=True, exist_ok=True)

    retrieval_rows: list[dict[str, object]] = []
    sector_rows: list[dict[str, object]] = []
    for method, report in retrieval.items():
        if report.get("method") != method:
            raise EvaluationReportError(f"Retrieval method mismatch for {method}")
        overall = report.get("overall")
        sectors = report.get("by_sector")
        if not isinstance(overall, dict) or not isinstance(sectors, dict):
            raise EvaluationReportError(f"Retrieval result is incomplete for {method}")
        retrieval_rows.append(
            {"method": method}
            | {
                metric: _number(overall.get(metric), label=f"{method}.{metric}")
                for metric in RETRIEVAL_METRICS
            }
        )
        for sector, metrics in sorted(sectors.items()):
            if not isinstance(metrics, dict):
                raise EvaluationReportError(f"Sector metrics are invalid for {method}.{sector}")
            sector_rows.append(
                {"method": method, "sector": sector}
                | {
                    metric: _number(metrics.get(metric), label=f"{method}.{sector}.{metric}")
                    for metric in RETRIEVAL_METRICS
                }
            )

    eligibility_metrics = {
        key: _number(value, label=f"eligibility.{key}")
        for key, value in eligibility.items()
        if value is not None
    }
    by_variant = agents.get("by_variant")
    if not isinstance(by_variant, dict) or not by_variant:
        raise EvaluationReportError("Agent result has no system variants")
    agent_rows: list[dict[str, object]] = []
    for variant, metrics in sorted(by_variant.items()):
        if not isinstance(metrics, dict):
            raise EvaluationReportError(f"Agent metrics are invalid for {variant}")
        agent_rows.append(
            {"variant": variant}
            | {
                key: _number(value, label=f"agents.{variant}.{key}")
                for key, value in metrics.items()
            }
        )

    artifacts = [
        output_dir / "retrieval-overall.csv",
        output_dir / "retrieval-by-sector.csv",
        output_dir / "eligibility.csv",
        output_dir / "agents-by-variant.csv",
        output_dir / "retrieval-overall.png",
        output_dir / "retrieval-ndcg-by-sector.png",
        output_dir / "eligibility-safety.png",
        output_dir / "agents-quality.png",
        output_dir / "agents-operations.png",
        output_dir / "summary.md",
    ]
    _write_csv(artifacts[0], ["method", *RETRIEVAL_METRICS], retrieval_rows)
    _write_csv(artifacts[1], ["method", "sector", *RETRIEVAL_METRICS], sector_rows)
    _write_csv(
        artifacts[2],
        ["metric", "value"],
        [{"metric": key, "value": value} for key, value in eligibility_metrics.items()],
    )
    agent_fields = [
        "variant",
        *sorted({key for row in agent_rows for key in row if key != "variant"}),
    ]
    _write_csv(artifacts[3], agent_fields, agent_rows)

    _bar_chart(
        artifacts[4],
        title="Retrieval baseline comparison",
        categories=list(RETRIEVAL_METHODS),
        series={
            metric: [float(row[metric]) for row in retrieval_rows]
            for metric in ("recall_at_10", "mrr", "ndcg_at_10")
        },
        ylabel="score",
    )
    sectors = sorted({str(row["sector"]) for row in sector_rows})
    _bar_chart(
        artifacts[5],
        title="nDCG@10 by sector",
        categories=sectors,
        series={
            method: [
                float(
                    next(
                        row["ndcg_at_10"]
                        for row in sector_rows
                        if row["method"] == method and row["sector"] == sector
                    )
                )
                for sector in sectors
            ]
            for method in RETRIEVAL_METHODS
        },
        ylabel="nDCG@10",
    )
    safety_keys = [
        key
        for key in ("macro_f1", "false_eligible_rate", "unknown_accuracy", "evidence_coverage")
        if key in eligibility_metrics
    ]
    _bar_chart(
        artifacts[6],
        title="Eligibility quality and safety",
        categories=safety_keys,
        series={"eligibility": [eligibility_metrics[key] for key in safety_keys]},
        ylabel="score or rate",
    )
    quality_keys = (
        "citation_precision",
        "claim_faithfulness",
        "unknown_accuracy",
        "schema_validation_success_rate",
    )
    _bar_chart(
        artifacts[7],
        title="Controlled-system quality by variant",
        categories=[str(row["variant"]) for row in agent_rows],
        series={key: [float(row[key]) for row in agent_rows] for key in quality_keys},
        ylabel="score",
    )
    _operation_chart(artifacts[8], agent_rows)

    commit = str(run_manifest.get("git_commit", "UNKNOWN"))
    as_of = str(run_manifest.get("as_of", "UNKNOWN"))
    artifacts[9].write_text(
        "# Generated evaluation summary\n\n"
        f"- Git commit: `{commit}`\n"
        f"- Catalog as-of date: `{as_of}`\n"
        "- Source: frozen evaluation JSON files in the parent directory.\n\n"
        "The CSV tables and PNG figures are generated directly from measured outputs. "
        "Interpretation and causal claims require human review; this generator does not "
        "declare a winning method.\n",
        encoding="utf-8",
    )
    return artifacts
