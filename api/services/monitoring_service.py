"""Business logic for the `monitoring` block of GET /system/status.
Reads the latest OFFLINE monitoring report (src/monitoring/runner.py) and
combines it with the LIVE operational snapshot for this API process.
Never fails /system/status just because monitoring has never run (Stage
9 §12) — if no report exists yet, every category status is explicitly
NOT_RUN rather than a fabricated "healthy"."""
from __future__ import annotations

from src.monitoring.operational import OperationalMetrics
from src.monitoring.reports import read_latest_report
from src.monitoring.schemas import NOT_RUN


def build_monitoring_status(operational_metrics: OperationalMetrics, model_available: bool) -> dict:
    report = read_latest_report()
    operational = operational_metrics.snapshot(model_available)

    if report is None:
        return {
            "available": False,
            "last_run_at": None,
            "dataset_type": None,
            "data_quality_status": NOT_RUN,
            "data_drift_status": NOT_RUN,
            "prediction_drift_status": NOT_RUN,
            "performance_status": NOT_RUN,
            "decision": NOT_RUN,
            "operational": operational,
        }

    return {
        "available": True,
        "last_run_at": report.get("monitoring_timestamp"),
        "dataset_type": report.get("dataset_type"),
        "data_quality_status": report.get("data_quality_status", NOT_RUN),
        "data_drift_status": report.get("data_drift_status", NOT_RUN),
        "prediction_drift_status": report.get("prediction_drift_status", NOT_RUN),
        "performance_status": report.get("performance_status", NOT_RUN),
        "decision": report.get("decision", NOT_RUN),
        "operational": operational,
    }
