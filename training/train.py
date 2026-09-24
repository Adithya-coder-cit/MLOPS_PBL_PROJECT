"""Stage 4: train and evaluate the primary (XGBoost) and baseline
(Random Forest) disruption-prediction models against the Stage 3
DVC-versioned processed dataset. Does not regenerate or modify that
dataset — train/val/test.parquet are loaded read-only.

Run: python -m training.train
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import mlflow.xgboost
import yaml
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier

from training.data_loader import PROCESSED_DIR, TARGET_COLUMN, load_processed_datasets
from training.evaluate import (
    calibration_summary,
    compute_metrics,
    predicted_probability_distribution,
    threshold_sensitivity,
)
from training.feature_importance import (
    random_forest_feature_names,
    random_forest_importance,
    summarize_importance,
    xgboost_gain_importance,
)
from training.imbalance import compute_class_distribution, decide_imbalance_strategy
from training.prepare_inputs import ALL_FEATURES, build_random_forest_matrix, build_xgboost_matrix, get_target
from training.reproducibility import capture_run_metadata
from training.tune import tune_random_forest, tune_xgboost

logger = logging.getLogger("routewise.training.train")

MODELS_DIR = Path("models")
PARAMS_PATH = Path("params.yaml")


def load_params() -> dict:
    return yaml.safe_load(PARAMS_PATH.read_text(encoding="utf-8"))


def main(processed_dir: Path = PROCESSED_DIR) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    params = load_params()
    training_cfg = params["training"]
    selection_metric = training_cfg["selection_metric"]
    threshold = training_cfg["decision_threshold"]

    logger.info("Loading Stage 3 processed datasets from %s (read-only)", processed_dir)
    data = load_processed_datasets(processed_dir)
    train_df, val_df, test_df = data.train, data.val, data.test

    # --- class distributions (§5) ---
    y_train, y_val, y_test = (get_target(df, TARGET_COLUMN) for df in (train_df, val_df, test_df))
    dist = {
        "train": compute_class_distribution(y_train).to_dict(),
        "val": compute_class_distribution(y_val).to_dict(),
        "test": compute_class_distribution(y_test).to_dict(),
    }
    logger.info("Class distributions: %s", dist)

    imbalance_decision = decide_imbalance_strategy(
        compute_class_distribution(y_train), training_cfg["class_imbalance"]["ratio_threshold_for_weighting"]
    )
    logger.info("Imbalance strategy (train-only decision): %s", imbalance_decision)

    # --- model-specific inputs (§2: native NaN handling vs train-fit imputer) ---
    X_train_xgb, X_val_xgb, X_test_xgb = (build_xgboost_matrix(df) for df in (train_df, val_df, test_df))
    X_train_rf = build_random_forest_matrix(train_df, data.preprocessor)
    X_val_rf = build_random_forest_matrix(val_df, data.preprocessor)
    X_test_rf = build_random_forest_matrix(test_df, data.preprocessor)
    rf_feature_names = random_forest_feature_names(data.preprocessor)

    # --- §3 baseline Random Forest: reasonable config, no tuning ---
    rf_base_params = dict(params["model"]["baseline"]["params"])
    if imbalance_decision["sklearn_class_weight"]:
        rf_base_params["class_weight"] = imbalance_decision["sklearn_class_weight"]

    logger.info("Training baseline Random Forest (untuned): %s", rf_base_params)
    t0 = time.perf_counter()
    rf_baseline_model = RandomForestClassifier(**rf_base_params)
    rf_baseline_model.fit(X_train_rf, y_train)
    rf_baseline_time = time.perf_counter() - t0
    rf_baseline_val_metrics = compute_metrics(y_val, rf_baseline_model.predict_proba(X_val_rf)[:, 1], threshold)
    logger.info("RF baseline val %s=%.4f (%.1fs)", selection_metric, rf_baseline_val_metrics[selection_metric],
                rf_baseline_time)

    # --- §4 primary XGBoost: default config, reference point before tuning ---
    xgb_base_params = dict(params["model"]["primary"]["params"])
    if imbalance_decision["strategy"] == "class_weighting":
        xgb_base_params["scale_pos_weight"] = imbalance_decision["scale_pos_weight"]

    logger.info("Training default XGBoost (untuned): %s", xgb_base_params)
    t0 = time.perf_counter()
    xgb_baseline_model = XGBClassifier(**xgb_base_params, enable_categorical=True, tree_method="hist")
    xgb_baseline_model.fit(X_train_xgb, y_train)
    xgb_baseline_time = time.perf_counter() - t0
    xgb_baseline_val_metrics = compute_metrics(y_val, xgb_baseline_model.predict_proba(X_val_xgb)[:, 1], threshold)
    logger.info("XGBoost default val %s=%.4f (%.1fs)", selection_metric, xgb_baseline_val_metrics[selection_metric],
                xgb_baseline_time)

    # --- §6 modest hyperparameter search, selected on VAL only ---
    logger.info("Tuning Random Forest (%d configs)", len(params["model"]["baseline"]["search_grid"]))
    rf_tuning = tune_random_forest(
        X_train_rf, y_train, X_val_rf, y_val,
        params["model"]["baseline"]["search_grid"], rf_base_params, selection_metric,
    )
    logger.info("Tuning XGBoost (%d configs)", len(params["model"]["primary"]["search_grid"]))
    xgb_tuning = tune_xgboost(
        X_train_xgb, y_train, X_val_xgb, y_val,
        params["model"]["primary"]["search_grid"], xgb_base_params, selection_metric,
    )

    # Final candidate per family = best of {baseline default, tuning trials} by val selection_metric.
    rf_candidates = [
        {"label": "baseline", "params": rf_base_params, "val_score": rf_baseline_val_metrics[selection_metric],
         "model": rf_baseline_model, "training_time_seconds": rf_baseline_time},
        {"label": "tuned", "params": {**rf_base_params, **rf_tuning["best_params"]},
         "val_score": rf_tuning["best_val_score"], "model": rf_tuning["best_model"],
         "training_time_seconds": rf_tuning["best_training_time_seconds"]},
    ]
    rf_final = max(rf_candidates, key=lambda c: c["val_score"])

    xgb_candidates = [
        {"label": "baseline", "params": xgb_base_params, "val_score": xgb_baseline_val_metrics[selection_metric],
         "model": xgb_baseline_model, "training_time_seconds": xgb_baseline_time},
        {"label": "tuned", "params": {**xgb_base_params, **xgb_tuning["best_params"]},
         "val_score": xgb_tuning["best_val_score"], "model": xgb_tuning["best_model"],
         "training_time_seconds": xgb_tuning["best_training_time_seconds"]},
    ]
    xgb_final = max(xgb_candidates, key=lambda c: c["val_score"])

    logger.info("Final RF candidate: %s (val %s=%.4f)", rf_final["label"], selection_metric, rf_final["val_score"])
    logger.info("Final XGBoost candidate: %s (val %s=%.4f)", xgb_final["label"], selection_metric,
                xgb_final["val_score"])

    # --- §7/§8 validation results, then ONE-TIME test evaluation ---
    rf_val_full = compute_metrics(y_val, rf_final["model"].predict_proba(X_val_rf)[:, 1], threshold)
    xgb_val_full = compute_metrics(y_val, xgb_final["model"].predict_proba(X_val_xgb)[:, 1], threshold)

    logger.info("Evaluating final candidates on TEST — once, no further tuning after this")
    rf_test_prob = rf_final["model"].predict_proba(X_test_rf)[:, 1]
    xgb_test_prob = xgb_final["model"].predict_proba(X_test_xgb)[:, 1]
    rf_test_full = compute_metrics(y_test, rf_test_prob, threshold)
    xgb_test_full = compute_metrics(y_test, xgb_test_prob, threshold)

    rf_val_prob = rf_final["model"].predict_proba(X_val_rf)[:, 1]
    xgb_val_prob = xgb_final["model"].predict_proba(X_val_xgb)[:, 1]

    diagnostics = {
        "random_forest": {
            "val_probability_distribution": predicted_probability_distribution(rf_val_prob),
            "test_probability_distribution": predicted_probability_distribution(rf_test_prob),
            "val_threshold_sensitivity": threshold_sensitivity(y_val.to_numpy(), rf_val_prob),
            "val_calibration": calibration_summary(y_val.to_numpy(), rf_val_prob),
        },
        "xgboost": {
            "val_probability_distribution": predicted_probability_distribution(xgb_val_prob),
            "test_probability_distribution": predicted_probability_distribution(xgb_test_prob),
            "val_threshold_sensitivity": threshold_sensitivity(y_val.to_numpy(), xgb_val_prob),
            "val_calibration": calibration_summary(y_val.to_numpy(), xgb_val_prob),
        },
    }

    # --- §11 feature importance ---
    rf_importance = random_forest_importance(rf_final["model"], rf_feature_names)
    xgb_importance = xgboost_gain_importance(xgb_final["model"], ALL_FEATURES)
    importance_summary = {
        "random_forest": summarize_importance(rf_importance, "importance"),
        "xgboost": summarize_importance(xgb_importance, "gain"),
    }

    # --- §9 reproducibility ---
    run_metadata = capture_run_metadata(data.dataset_metadata, data.feature_manifest, training_cfg["seed"])

    # --- §12 artifacts ---
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    (MODELS_DIR / "candidates").mkdir(exist_ok=True)
    (MODELS_DIR / "evaluation").mkdir(exist_ok=True)
    (MODELS_DIR / "feature_importance").mkdir(exist_ok=True)

    joblib.dump(rf_baseline_model, MODELS_DIR / "candidates" / "random_forest_baseline.joblib")
    joblib.dump(rf_final["model"], MODELS_DIR / "candidates" / "random_forest_tuned.joblib")
    joblib.dump(xgb_baseline_model, MODELS_DIR / "candidates" / "xgboost_baseline.joblib")
    joblib.dump(xgb_final["model"], MODELS_DIR / "candidates" / "xgboost_tuned.joblib")

    def _clean_params(p: dict) -> dict:
        return {k: v for k, v in p.items() if k != "model"}

    evaluation_payload = {
        "class_distributions": dist,
        "imbalance_decision": imbalance_decision,
        "selection_metric": selection_metric,
        "decision_threshold": threshold,
        "random_forest": {
            "final_candidate_label": rf_final["label"], "params": _clean_params(rf_final["params"]),
            "training_time_seconds": rf_final["training_time_seconds"],
            "feature_count": len(rf_feature_names),
            "baseline_val_metrics": rf_baseline_val_metrics,
            "validation_metrics": rf_val_full, "test_metrics": rf_test_full,
            "tuning_trials": rf_tuning["trials"],
        },
        "xgboost": {
            "final_candidate_label": xgb_final["label"], "params": _clean_params(xgb_final["params"]),
            "training_time_seconds": xgb_final["training_time_seconds"],
            "feature_count": len(ALL_FEATURES),
            "baseline_val_metrics": xgb_baseline_val_metrics,
            "validation_metrics": xgb_val_full, "test_metrics": xgb_test_full,
            "tuning_trials": xgb_tuning["trials"],
        },
        "diagnostics": diagnostics,
        "run_metadata": run_metadata,
    }
    (MODELS_DIR / "evaluation" / "evaluation.json").write_text(json.dumps(evaluation_payload, indent=2, default=str),
                                                                encoding="utf-8")

    comparison_table = [
        {"model": "random_forest", "candidate": rf_final["label"], "precision": rf_test_full["precision"],
         "recall": rf_test_full["recall"], "f1": rf_test_full["f1"], "roc_auc": rf_test_full["roc_auc"],
         "pr_auc": rf_test_full["pr_auc"], "training_time_seconds": rf_final["training_time_seconds"]},
        {"model": "xgboost", "candidate": xgb_final["label"], "precision": xgb_test_full["precision"],
         "recall": xgb_test_full["recall"], "f1": xgb_test_full["f1"], "roc_auc": xgb_test_full["roc_auc"],
         "pr_auc": xgb_test_full["pr_auc"], "training_time_seconds": xgb_final["training_time_seconds"]},
    ]
    (MODELS_DIR / "evaluation" / "model_comparison.json").write_text(
        json.dumps({"basis": "test set (single evaluation, post model-selection)", "table": comparison_table},
                   indent=2), encoding="utf-8"
    )

    (MODELS_DIR / "feature_importance" / "random_forest_importance.json").write_text(
        json.dumps(importance_summary["random_forest"], indent=2), encoding="utf-8"
    )
    (MODELS_DIR / "feature_importance" / "xgboost_importance.json").write_text(
        json.dumps(importance_summary["xgboost"], indent=2), encoding="utf-8"
    )
    (MODELS_DIR / "run_metadata.json").write_text(json.dumps(run_metadata, indent=2, default=str), encoding="utf-8")

    # --- MLflow tracking ---
    mlflow.set_tracking_uri(params["mlflow"]["tracking_uri"])
    mlflow.set_experiment(params["mlflow"]["experiment_name"])
    with mlflow.start_run(run_name="stage4_training"):
        mlflow.set_tags({"git_commit_sha": str(run_metadata["git_commit_sha"]),
                          "dataset_generation_seed": str(run_metadata["dataset_metadata"].get("generation_seed"))})
        mlflow.log_params({"selection_metric": selection_metric, "decision_threshold": threshold,
                            "imbalance_strategy": imbalance_decision["strategy"]})
        mlflow.log_dict(dist, "class_distributions.json")

        with mlflow.start_run(run_name="random_forest_baseline", nested=True):
            mlflow.log_params(rf_base_params)
            mlflow.log_metrics({f"val_{k}": v for k, v in rf_baseline_val_metrics.items()
                                 if isinstance(v, int | float)})

        with mlflow.start_run(run_name="random_forest_final", nested=True):
            mlflow.log_params(_clean_params(rf_final["params"]))
            mlflow.log_metrics({f"val_{k}": v for k, v in rf_val_full.items() if isinstance(v, int | float)})
            mlflow.log_metrics({f"test_{k}": v for k, v in rf_test_full.items() if isinstance(v, int | float)})
            mlflow.sklearn.log_model(rf_final["model"], "model")
            mlflow.log_dict(importance_summary["random_forest"], "feature_importance.json")

        with mlflow.start_run(run_name="xgboost_baseline", nested=True):
            mlflow.log_params(xgb_base_params)
            mlflow.log_metrics({f"val_{k}": v for k, v in xgb_baseline_val_metrics.items()
                                 if isinstance(v, int | float)})

        with mlflow.start_run(run_name="xgboost_final", nested=True):
            mlflow.log_params(_clean_params(xgb_final["params"]))
            mlflow.log_metrics({f"val_{k}": v for k, v in xgb_val_full.items() if isinstance(v, int | float)})
            mlflow.log_metrics({f"test_{k}": v for k, v in xgb_test_full.items() if isinstance(v, int | float)})
            mlflow.xgboost.log_model(xgb_final["model"], "model")
            mlflow.log_dict(importance_summary["xgboost"], "feature_importance.json")

    logger.info("Stage 4 complete. Artifacts under %s", MODELS_DIR)
    return {
        "class_distributions": dist, "imbalance_decision": imbalance_decision,
        "random_forest": {"validation_metrics": rf_val_full, "test_metrics": rf_test_full,
                           "final_candidate_label": rf_final["label"]},
        "xgboost": {"validation_metrics": xgb_val_full, "test_metrics": xgb_test_full,
                    "final_candidate_label": xgb_final["label"]},
        "comparison_table": comparison_table,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    args = parser.parse_args()
    main(Path(args.processed_dir))
