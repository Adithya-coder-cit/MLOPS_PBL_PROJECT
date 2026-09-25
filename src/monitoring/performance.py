"""Performance monitoring: reuses training/evaluate.py's exact metric
definitions (precision/recall/F1/ROC-AUC/PR-AUC) — never re-derives them,
so "performance" means the same thing here as it did at training time.

Only runs when ground-truth labels (disruption_flag) are actually present
on the current batch (Stage 9 §2D) — otherwise it explicitly reports that
evaluation is unavailable rather than fabricating a metric.
"""
from __future__ import annotations

import numpy as np

from training.evaluate import compute_metrics

LABEL_UNAVAILABLE_MESSAGE = "Performance evaluation unavailable because ground-truth labels are not yet available."


def run_performance_monitoring(
    y_true: np.ndarray | None,
    y_prob: np.ndarray | None,
    baseline_metrics: dict,
    regression_tolerance: dict,
    decision_threshold: float = 0.5,
) -> dict:
    if y_true is None or y_prob is None or len(y_true) == 0:
        return {
            "available": False, "message": LABEL_UNAVAILABLE_MESSAGE,
            "current_metrics": None, "baseline_metrics": baseline_metrics, "regressions": {},
        }

    current_metrics = compute_metrics(y_true, y_prob, threshold=decision_threshold)
    regressions = {}
    for metric, tolerance in regression_tolerance.items():
        baseline_value = baseline_metrics.get(metric)
        current_value = current_metrics.get(metric)
        if baseline_value is None or current_value is None:
            continue
        delta = current_value - baseline_value
        regressions[metric] = {
            "baseline": baseline_value, "current": current_value, "delta": delta,
            "regression_tolerance": tolerance, "regressed": delta < -tolerance,
        }
    return {
        "available": True, "message": None,
        "current_metrics": current_metrics, "baseline_metrics": baseline_metrics, "regressions": regressions,
    }


def performance_status(result: dict) -> str:
    if not result["available"]:
        return "NOT_AVAILABLE"
    return "DEGRADED" if any(r["regressed"] for r in result["regressions"].values()) else "OK"
