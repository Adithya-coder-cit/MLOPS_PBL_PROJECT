"""Evaluation metrics. Reports more than accuracy, since disruption is the
minority class and accuracy alone would be misleading (a model predicting
"no disruption" for everything would already score ~73% accuracy).
"""
from __future__ import annotations

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

METRIC_RATIONALE = {
    "accuracy": "Reported for completeness, but misleading alone under ~27% positive-class "
                "prevalence — a trivial always-negative model would already score ~0.73.",
    "precision": "Of the stop-events flagged as disruptions, how many actually were — controls "
                 "false-alarm cost (unnecessary rerouting).",
    "recall": "Of the actual disruptions, how many were caught — controls missed-disruption cost, "
              "which is the operational risk this system exists to reduce.",
    "f1": "Harmonic mean of precision/recall — a single balance-point number, sensitive to the "
          "chosen decision threshold (0.5 here).",
    "roc_auc": "Threshold-independent ranking quality, but can look optimistic under class "
               "imbalance since it weights the (large) negative class equally.",
    "pr_auc": "Threshold-independent, but focused on the positive (minority) class — the more "
              "informative ranking metric here, and used as the model-selection criterion.",
}


def compute_metrics(y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.5) -> dict:
    y_pred = (y_prob >= threshold).astype(int)
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    return {
        "threshold": threshold,
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_prob)),
        "pr_auc": float(average_precision_score(y_true, y_prob)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "metric_rationale": METRIC_RATIONALE,
    }


def predicted_probability_distribution(y_prob: np.ndarray) -> dict:
    return {
        "min": float(np.min(y_prob)), "max": float(np.max(y_prob)),
        "mean": float(np.mean(y_prob)), "median": float(np.median(y_prob)),
        "std": float(np.std(y_prob)),
        "percentiles": {str(p): float(np.percentile(y_prob, p)) for p in [5, 25, 50, 75, 95]},
    }


def threshold_sensitivity(y_true: np.ndarray, y_prob: np.ndarray, thresholds: list[float] | None = None) -> list[dict]:
    """Precision/recall/F1 across a range of thresholds — computed on
    whichever split is passed in. Only ever called with val, never test
    (see training/train.py — the operating threshold is fixed at 0.5 by
    policy, this is diagnostic only, not used to pick a different one)."""
    thresholds = thresholds or [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    rows = []
    for t in thresholds:
        y_pred = (y_prob >= t).astype(int)
        rows.append({
            "threshold": t,
            "precision": float(precision_score(y_true, y_pred, zero_division=0)),
            "recall": float(recall_score(y_true, y_pred, zero_division=0)),
            "f1": float(f1_score(y_true, y_pred, zero_division=0)),
            "n_predicted_positive": int(y_pred.sum()),
        })
    return rows


def calibration_summary(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> dict:
    try:
        prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy="quantile")
    except ValueError:
        prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy="uniform")
    return {
        "n_bins": len(prob_true),
        "mean_predicted_probability_per_bin": [float(x) for x in prob_pred],
        "observed_positive_rate_per_bin": [float(x) for x in prob_true],
        "note": "Closer prob_pred~observed_rate per bin indicates better calibration; "
                "not a single summary statistic by design, for direct inspection.",
    }
