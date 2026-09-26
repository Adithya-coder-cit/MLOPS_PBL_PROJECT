"""Stage 10 §17: the controlled boundary between Stage 9 monitoring and
Stage 10 retraining. This module NEVER executes a shell command, invokes
a workflow, or triggers training itself — it only reads the last
monitoring decision (src.monitoring.reports.read_latest_report) and
answers one question: is retraining recommended right now?

The CI workflow boundary that actually acts on this (invoking
retraining.yml via workflow_dispatch) lives entirely in
.github/workflows/monitoring.yml, which reads this script's structured
output and makes the call itself — this script has no ability to do so.

Run: python -m training.retraining_trigger
Writes `retraining_recommended`/`decision`/`reason` to $GITHUB_OUTPUT if
set (GitHub Actions convention); otherwise prints JSON to stdout.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from src.monitoring.reports import read_latest_report
from src.monitoring.schemas import RETRAINING_RECOMMENDED

logger = logging.getLogger("routewise.training.retraining_trigger")


def check_retraining_trigger(report: dict | None = None) -> dict:
    report = report if report is not None else read_latest_report()
    if report is None:
        return {
            "retraining_recommended": False,
            "decision": "NOT_RUN",
            "reasons": ["No monitoring report exists yet — run python -m src.monitoring.runner first."],
            "monitoring_timestamp": None,
        }
    decision = report.get("decision", "NOT_RUN")
    return {
        "retraining_recommended": decision == RETRAINING_RECOMMENDED,
        "decision": decision,
        "reasons": report.get("decision_reasons", []),
        "monitoring_timestamp": report.get("monitoring_timestamp"),
    }


def _write_github_output(result: dict) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(f"retraining_recommended={'true' if result['retraining_recommended'] else 'false'}\n")
        f.write(f"decision={result['decision']}\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    result = check_retraining_trigger()
    _write_github_output(result)
    print(json.dumps(result, indent=2))
    if result["retraining_recommended"]:
        logger.info("Retraining IS recommended: %s", "; ".join(result["reasons"]))
    else:
        logger.info("Retraining is NOT recommended (decision=%s).", result["decision"])

    Path("models/retraining").mkdir(parents=True, exist_ok=True)
    Path("models/retraining/latest_trigger_check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
