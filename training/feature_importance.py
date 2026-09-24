"""Model explainability artifacts. Only ever computed over the modeling
feature set (training/prepare_inputs.py ALL_FEATURES) — identifiers and
diagnostic-only columns are never part of X, so they cannot appear here.

Feature importance shows what the model weighted most when splitting/
ranking — it is NOT evidence of a causal relationship between a feature
and disruption risk.
"""
from __future__ import annotations

import numpy as np


def xgboost_gain_importance(model, feature_names: list[str]) -> list[dict]:
    booster = model.get_booster()
    gain_scores = booster.get_score(importance_type="gain")
    rows = [{"feature": f, "gain": float(gain_scores.get(f, 0.0))} for f in feature_names]
    rows.sort(key=lambda r: r["gain"], reverse=True)
    return rows


def random_forest_importance(model, feature_names: list[str]) -> list[dict]:
    importances = model.feature_importances_
    rows = [{"feature": f, "importance": float(v)} for f, v in zip(feature_names, importances)]
    rows.sort(key=lambda r: r["importance"], reverse=True)
    return rows


def random_forest_feature_names(preprocessor) -> list[str]:
    return [str(n) for n in preprocessor.get_feature_names_out()]


def top_n(importance_rows: list[dict], n: int = 10) -> list[dict]:
    return importance_rows[:n]


CAUSALITY_DISCLAIMER = (
    "Feature importance reflects what the model used to reduce prediction error "
    "on this synthetic development dataset. It does NOT establish that a feature "
    "causes disruption — only that it was predictive within this data and model."
)


def summarize_importance(importance_rows: list[dict], value_key: str, n: int = 10) -> dict:
    top = top_n(importance_rows, n)
    return {
        "top_features": top,
        "top_feature_names": [r["feature"] for r in top],
        "total_importance_mass_top_n": float(np.sum([r[value_key] for r in top])),
        "causality_disclaimer": CAUSALITY_DISCLAIMER,
    }
