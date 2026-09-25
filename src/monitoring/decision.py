"""Deterministic monitoring decision policy (Stage 9 §10/§11). Stage 9
never retrains anything — it only classifies. The decision this module
returns is the signal a later stage would consume to trigger retraining;
that trigger is explicitly out of scope here.

Feature drift and prediction drift alone can only ever escalate to
REVIEW_REQUIRED, never straight to RETRAINING_RECOMMENDED — drift is NOT
equated with model failure. Only a measured PERFORMANCE regression can
trigger RETRAINING_RECOMMENDED. Every rule below is driven by
params.yaml monitoring.decision_policy, never hardcoded in this module.
"""
from __future__ import annotations

from src.monitoring.schemas import DEGRADED, DRIFT_DETECTED, FAIL, NO_ACTION, RETRAINING_RECOMMENDED, REVIEW_REQUIRED


def decide(
    data_quality_status: str,
    data_drift_status: str,
    prediction_drift_status: str,
    performance_status: str,
    policy: dict,
) -> tuple[str, list[str]]:
    if performance_status == DEGRADED and policy.get("retraining_recommended_if_performance_degraded", True):
        return RETRAINING_RECOMMENDED, [
            "Performance regression detected against the recorded training-time baseline."
        ]

    reasons: list[str] = []
    if data_quality_status == FAIL and policy.get("review_required_if_data_quality_fail", True):
        reasons.append("Data quality check(s) failed on the current batch.")
    if data_drift_status == DRIFT_DETECTED and policy.get("review_required_if_data_drift_detected", True):
        reasons.append(
            "Feature drift detected between reference and current data "
            "(not, by itself, evidence of model failure)."
        )
    if prediction_drift_status == DRIFT_DETECTED and policy.get("review_required_if_prediction_drift_detected", True):
        reasons.append(
            "Prediction drift detected between reference and current data "
            "(not, by itself, evidence of model failure)."
        )

    if reasons:
        return REVIEW_REQUIRED, reasons
    return NO_ACTION, ["No data quality failures, no drift, and no performance regression detected."]
