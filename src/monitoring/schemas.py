"""Structured, machine-readable monitoring result — the single output
shape every Stage 9 monitoring run produces. Read by GET /system/status
(api/services/monitoring_service.py) and intended to be the input Stage
10's retraining trigger consumes later; Stage 9 itself never retrains.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# This project has no production model and uses synthetic data throughout
# — every monitoring result is stamped with this constant so it can never
# be read as a claim about live Chennai transport conditions (Stage 9 §19).
DATASET_TYPE = "DEVELOPMENT/DEMO"

# --- per-category statuses ---
PASS = "PASS"
FAIL = "FAIL"
NO_DRIFT = "NO_DRIFT"
DRIFT_DETECTED = "DRIFT_DETECTED"
OK = "OK"
DEGRADED = "DEGRADED"
NOT_AVAILABLE = "NOT_AVAILABLE"
NOT_RUN = "NOT_RUN"

# --- monitoring decision (Stage 9 §10) ---
NO_ACTION = "NO_ACTION"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
RETRAINING_RECOMMENDED = "RETRAINING_RECOMMENDED"


@dataclass
class MonitoringResult:
    monitoring_timestamp: str
    dataset_type: str
    reference_dataset_version: str
    current_dataset_version: str
    reference_period: dict
    current_period: dict
    model_name: str | None
    model_version: str | None
    git_sha: str | None
    feature_manifest_version: str | None
    monitored_features: list[str]
    data_quality: dict
    data_quality_status: str
    data_drift: dict
    data_drift_status: str
    prediction_drift: dict
    prediction_drift_status: str
    performance: dict
    performance_status: str
    operational_status: str
    decision: str
    decision_reasons: list[str]
    overall_status: str
    html_reports: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "monitoring_timestamp": self.monitoring_timestamp,
            "dataset_type": self.dataset_type,
            "reference_dataset_version": self.reference_dataset_version,
            "current_dataset_version": self.current_dataset_version,
            "reference_period": self.reference_period,
            "current_period": self.current_period,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "git_sha": self.git_sha,
            "feature_manifest_version": self.feature_manifest_version,
            "monitored_features": self.monitored_features,
            "data_quality": self.data_quality,
            "data_quality_status": self.data_quality_status,
            "data_drift": self.data_drift,
            "data_drift_status": self.data_drift_status,
            "prediction_drift": self.prediction_drift,
            "prediction_drift_status": self.prediction_drift_status,
            "performance": self.performance,
            "performance_status": self.performance_status,
            "operational_status": self.operational_status,
            "decision": self.decision,
            "decision_reasons": self.decision_reasons,
            "overall_status": self.overall_status,
            "html_reports": self.html_reports,
        }
