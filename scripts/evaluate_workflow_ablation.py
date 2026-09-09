from __future__ import annotations

import argparse
import json
from pathlib import Path

from eu_funding_agents.evaluation.reproducibility import git_state
from eu_funding_agents.evaluation.workflow_ablation import workflow_ablation_report

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "evaluation" / "workflow-ablation.json"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate controlled workflow ablations")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict[str, object]:
    report = workflow_ablation_report()
    commit, dirty = git_state(ROOT)
    report.update({"git_commit": commit, "git_dirty": dirty})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(arguments()), indent=2))
