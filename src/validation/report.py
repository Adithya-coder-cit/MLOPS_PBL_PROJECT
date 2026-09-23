"""Build and persist the machine-readable validation report, and fail
loudly (raise) when any ERROR-level issue is present. Validation never
silently repairs data — a failing check stops the pipeline.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.validation.validators import ERROR, INFO, WARNING, ValidationIssue


class ValidationError(Exception):
    """Raised when one or more ERROR-level validation issues are found."""


def build_report(issues: list[ValidationIssue]) -> dict:
    by_level = {ERROR: [], WARNING: [], INFO: []}
    for issue in issues:
        by_level[issue.level].append(issue.to_dict())
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "errors": len(by_level[ERROR]),
            "warnings": len(by_level[WARNING]),
            "info": len(by_level[INFO]),
            "passed": len(by_level[ERROR]) == 0,
        },
        "errors": by_level[ERROR],
        "warnings": by_level[WARNING],
        "info": by_level[INFO],
    }


def write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def raise_if_errors(report: dict) -> None:
    if report["summary"]["errors"] > 0:
        messages = [f"[{e['table']}] {e['check']}: {e['message']}" for e in report["errors"]]
        raise ValidationError(
            f"{report['summary']['errors']} validation error(s) found — refusing to proceed:\n"
            + "\n".join(messages)
        )
