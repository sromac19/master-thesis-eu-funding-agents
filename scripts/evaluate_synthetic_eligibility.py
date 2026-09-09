from __future__ import annotations

import argparse
import json
from pathlib import Path

from eu_funding_agents.evaluation.reproducibility import git_state
from eu_funding_agents.evaluation.synthetic_eligibility import synthetic_eligibility_report

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "evaluation" / "synthetic-eligibility.json"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate controlled synthetic rule cases")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict[str, object]:
    report = synthetic_eligibility_report()
    commit, dirty = git_state(ROOT)
    report.update({"git_commit": commit, "git_dirty": dirty})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(arguments()), indent=2))
