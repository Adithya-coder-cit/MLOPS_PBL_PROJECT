"""Modest, reproducible hyperparameter search: a small curated list of
candidate configs (see params.yaml model.*.search_grid), each fit once on
TRAIN and scored once on VAL. No k-fold cross-validation — this is
temporal data, and random CV folds would re-shuffle across time, which is
exactly the leakage failure mode Stage 3 was built to avoid. The test set
is never touched during this search.
"""
from __future__ import annotations

import logging
import time

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier

from training.evaluate import compute_metrics

logger = logging.getLogger("routewise.training.tune")


def _score(y_val: np.ndarray, y_prob: np.ndarray, selection_metric: str) -> float:
    metrics = compute_metrics(y_val, y_prob)
    return metrics[selection_metric]


def _strip_models(trials: list[dict]) -> list[dict]:
    return [{k: v for k, v in t.items() if k != "model"} for t in trials]


def tune_xgboost(X_train, y_train, X_val, y_val, param_grid: list[dict], base_params: dict,
                  selection_metric: str) -> dict:
    trials = []
    for params in param_grid:
        full_params = {**base_params, **params}
        start = time.perf_counter()
        model = XGBClassifier(**full_params, enable_categorical=True, tree_method="hist")
        model.fit(X_train, y_train)
        elapsed = time.perf_counter() - start
        y_prob = model.predict_proba(X_val)[:, 1]
        score = _score(y_val, y_prob, selection_metric)
        trials.append({"params": params, "val_score": score, "training_time_seconds": elapsed, "model": model})
        logger.info("XGBoost trial %s -> val %s=%.4f (%.1fs)", params, selection_metric, score, elapsed)

    best = max(trials, key=lambda t: t["val_score"])
    return {"trials": _strip_models(trials), "best_params": best["params"], "best_val_score": best["val_score"],
            "best_model": best["model"], "best_training_time_seconds": best["training_time_seconds"]}


def tune_random_forest(X_train, y_train, X_val, y_val, param_grid: list[dict], base_params: dict,
                        selection_metric: str) -> dict:
    trials = []
    for params in param_grid:
        full_params = {**base_params, **params}
        start = time.perf_counter()
        model = RandomForestClassifier(**full_params)
        model.fit(X_train, y_train)
        elapsed = time.perf_counter() - start
        y_prob = model.predict_proba(X_val)[:, 1]
        score = _score(y_val, y_prob, selection_metric)
        trials.append({"params": params, "val_score": score, "training_time_seconds": elapsed, "model": model})
        logger.info("RandomForest trial %s -> val %s=%.4f (%.1fs)", params, selection_metric, score, elapsed)

    best = max(trials, key=lambda t: t["val_score"])
    return {"trials": _strip_models(trials), "best_params": best["params"], "best_val_score": best["val_score"],
            "best_model": best["model"], "best_training_time_seconds": best["training_time_seconds"]}
