"""Writes the machine-readable monitoring JSON report and reads it back
for the API (Stage 9 §12/§18). HTML reports (Evidently's own renderer)
are written alongside it but never committed — see the
data/interim/monitoring/.gitignore entry added for this stage.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.monitoring.schemas import MonitoringResult

MONITORING_DIR = Path("data/interim/monitoring")
LATEST_REPORT_PATH = MONITORING_DIR / "latest_monitoring_report.json"
HTML_REPORTS_DIR = MONITORING_DIR / "html_reports"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json_report(result: MonitoringResult, path: Path = LATEST_REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def read_latest_report(path: Path = LATEST_REPORT_PATH) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
