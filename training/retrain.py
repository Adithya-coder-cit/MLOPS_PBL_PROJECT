"""Stage 10 §1: deterministic retraining entry point.

Orchestrates EXISTING modules end to end — it contains no training or
promotion logic of its own:

  1. load the configured dataset          -> training.data_loader (via safety checks)
  2. validate data                        -> training.retraining_safety
  3. build features                       -> (already built; src.features.build_dataset is
                                               the feature pipeline, reused unchanged — see
                                               README "Retraining" for when to rerun it)
  4. train configured models              -> training.train.main()
  5. evaluate them                        -> training.train.main() (writes evaluation.json)
  6. log the run to MLflow                -> training.track_and_register.main()
  7. register the candidate               -> training.track_and_register.main()
  8. execute the promotion gate           -> training.promotion_gate (via track_and_register)
  9. promote only when configured         -> training.promote_model (only with --promotion-mode auto
                                               AND the gate actually passed)

Never trains on partially invalid data (safety checks run first, always,
even in --dry-run) and never promotes to Production implicitly — the
default --promotion-mode is "manual": a human runs training/promote_model.py
--confirm afterward. Production is a NONE state today and this script does
not fabricate one.

Run: python -m training.retrain [--dry-run] [--model {xgboost,random_forest,both}]
                                 [--promotion-mode {manual,auto}] [--dataset-version X]
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

import yaml

from training import promote_model, track_and_register, train
from training.data_loader import PROCESSED_DIR
from training.mlflow_tracking import get_production_test_metrics
from training.reproducibility import capture_run_metadata
from training.retraining_safety import SafetyCheckError, raise_if_unsafe, run_safety_checks

logger = logging.getLogger("routewise.training.retrain")

PARAMS_PATH = Path("params.yaml")
MODELS_DIR = Path("models")
RETRAINING_DIR = MODELS_DIR / "retraining"
LATEST_REPORT_PATH = RETRAINING_DIR / "latest_retrain_report.json"

MODEL_CHOICES = {"xgboost", "random_forest", "both"}
PROMOTION_MODES = {"manual", "auto"}

DECISION_TRAINING = "TRAINING"
DECISION_TRAINED_NO_CANDIDATE_VALIDATED = "TRAINED_NO_CANDIDATE_VALIDATED"
DECISION_TRAINED_VALIDATED = "TRAINED_CANDIDATE_VALIDATED"
DECISION_TRAINED_PROMOTED = "TRAINED_AND_PROMOTED"
DECISION_DRY_RUN = "DRY_RUN_OK"
DECISION_REJECTED_UNSAFE = "REJECTED_UNSAFE"


class RetrainRefused(Exception):
    """Raised when retraining stops safely before training/promotion —
    e.g. a failed safety check or an explicit dataset-version mismatch."""


def _resolve_model_selection(model: str) -> set[str]:
    if model == "both":
        return {"xgboost", "random_forest"}
    return {model}


def _check_dataset_version(requested: str | None, processed_dir: Path) -> None:
    if requested is None:
        return
    dataset_metadata = json.loads((processed_dir / "dataset_metadata.json").read_text(encoding="utf-8"))
    actual = dataset_metadata.get("dataset_version")
    if actual != requested:
        raise RetrainRefused(
            f"Requested dataset_version='{requested}' does not match the currently processed "
            f"dataset_version='{actual}'. This project has no multi-version dataset store — "
            "regenerate data/processed/ (src.features.build_dataset) for the intended version first."
        )


def _current_production_snapshot(registered_model_name: str, tracking_uri: str) -> dict:
    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()
    metrics = get_production_test_metrics(client, registered_model_name)
    return {"production_model_exists": metrics is not None, "production_test_metrics": metrics}


def _write_report(report: dict) -> Path:
    RETRAINING_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = report["retraining_timestamp"].replace(":", "").replace("-", "")
    run_path = RETRAINING_DIR / f"retrain_{timestamp}.json"
    run_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    LATEST_REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return run_path


def retrain(
    params_config: dict | None = None,
    model: str = "both",
    promotion_mode: str = "manual",
    dataset_version: str | None = None,
    dry_run: bool = False,
    processed_dir: Path = PROCESSED_DIR,
    models_dir: Path = MODELS_DIR,
) -> dict:
    if model not in MODEL_CHOICES:
        raise ValueError(f"Unknown model '{model}', expected one of {MODEL_CHOICES}")
    if promotion_mode not in PROMOTION_MODES:
        raise ValueError(f"Unknown promotion_mode '{promotion_mode}', expected one of {PROMOTION_MODES}")

    params_config = params_config or yaml.safe_load(PARAMS_PATH.read_text(encoding="utf-8"))
    selected_models = _resolve_model_selection(model)
    tracking_uri = params_config["mlflow"]["tracking_uri"]
    registered_model_name = params_config["mlflow"]["registered_model_name"]

    report: dict = {
        "retraining_timestamp": datetime.now().isoformat(timespec="seconds"),
        "requested_model": model,
        "selected_models": sorted(selected_models),
        "promotion_mode": promotion_mode,
        "requested_dataset_version": dataset_version,
        "dry_run": dry_run,
        "decision": DECISION_TRAINING,
    }

    # --- §3 safety checks (ALWAYS run, even in dry-run) ---
    logger.info("Running retraining safety checks")
    issues = run_safety_checks(params_config, processed_dir)
    report["safety_checks"] = [i.to_dict() for i in issues]
    try:
        raise_if_unsafe(issues)
        _check_dataset_version(dataset_version, processed_dir)
    except (SafetyCheckError, RetrainRefused) as e:
        report["decision"] = DECISION_REJECTED_UNSAFE
        report["stop_reason"] = str(e)
        _write_report(report)
        logger.error("Retraining REFUSED: %s", e)
        raise

    # --- §4 lineage (recorded regardless of dry-run) ---
    dataset_metadata = json.loads((processed_dir / "dataset_metadata.json").read_text(encoding="utf-8"))
    feature_manifest = json.loads((processed_dir / "feature_manifest.json").read_text(encoding="utf-8"))
    report["lineage"] = capture_run_metadata(dataset_metadata, feature_manifest, params_config["training"]["seed"])

    # --- current production state, for the plan / comparison ---
    report["production_before"] = _current_production_snapshot(registered_model_name, tracking_uri)

    if dry_run:
        report["decision"] = DECISION_DRY_RUN
        report["plan"] = {
            "would_train": sorted(selected_models),
            "would_register_as": "Candidate",
            "would_evaluate_gate_against": (
                "current production model" if report["production_before"]["production_model_exists"]
                else "minimum_thresholds only (no production model exists)"
            ),
            "would_promote_to_production": (
                promotion_mode == "auto" and "if, and only if, the promotion gate passes for the best candidate"
            ),
        }
        _write_report(report)
        logger.info("Dry run complete — no training performed, no model registered or promoted.")
        return report

    # --- §4/§5/§6 train (reuses training.train unchanged) ---
    logger.info("Training configured models (reusing training.train, no duplicated logic)")
    train_summary = train.main(processed_dir)
    report["train_summary"] = {
        "random_forest_test_metrics": train_summary["random_forest"]["test_metrics"],
        "xgboost_test_metrics": train_summary["xgboost"]["test_metrics"],
    }

    # --- §7/§8/§9 log to MLflow, register, run the promotion gate (reuses training.track_and_register unchanged) ---
    logger.info("Logging + registering selected model(s): %s", selected_models)
    registration = track_and_register.main(processed_dir, models_dir, models=selected_models)
    report["registration"] = registration

    validated = {
        name: summary for name, summary in registration.items()
        if name in selected_models and summary is not None and summary["lifecycle_stage"] == "Validated"
    }

    if not validated:
        report["decision"] = DECISION_TRAINED_NO_CANDIDATE_VALIDATED
        _write_report(report)
        logger.warning("No candidate passed the promotion gate — remains Candidate. See registration.*.gate_result.")
        return report

    report["decision"] = DECISION_TRAINED_VALIDATED

    if promotion_mode == "auto":
        # Deterministic tie-break among gate-passing candidates: the same
        # selection_metric training.train.py already uses for model
        # selection (never a new, ad hoc criterion).
        selection_metric = params_config["training"]["selection_metric"]
        best_name = max(validated, key=lambda n: train_summary[n]["test_metrics"][selection_metric])
        best_version = validated[best_name]["model_version"]
        logger.info("Auto-promotion mode: promoting best validated candidate '%s' v%s to production",
                    best_name, best_version)
        promote_model.promote(registered_model_name, best_version, tracking_uri, confirm=True)
        report["decision"] = DECISION_TRAINED_PROMOTED
        report["promoted"] = {"model_label": best_name, "model_version": best_version}

    _write_report(report)
    logger.info("Retraining complete: decision=%s", report["decision"])
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    _cfg = yaml.safe_load(PARAMS_PATH.read_text(encoding="utf-8"))
    _retraining_cfg = _cfg.get("retraining", {})

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", choices=sorted(MODEL_CHOICES),
                         default=_retraining_cfg.get("default_model_selection", "both"))
    parser.add_argument("--promotion-mode", choices=sorted(PROMOTION_MODES),
                         default=_retraining_cfg.get("default_promotion_mode", "manual"))
    parser.add_argument("--dataset-version", default=None)
    args = parser.parse_args()

    retrain(
        params_config=_cfg, model=args.model, promotion_mode=args.promotion_mode,
        dataset_version=args.dataset_version, dry_run=args.dry_run,
    )
