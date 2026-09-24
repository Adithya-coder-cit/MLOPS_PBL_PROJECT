"""MLflow experiment tracking + model registry wiring around the EXISTING
Stage 4 training artifacts. Does not retrain — reads the real, already
computed models/evaluation/* and models/candidates/*.joblib produced by
`python -m training.train`, and logs them faithfully to MLflow: full
parameters, val/test metrics (kept separate), data/code lineage tags,
artifacts, a validated model signature, and a registered model version
tagged "Candidate" (never auto-promoted to "Production").
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import mlflow
import numpy as np
from mlflow.exceptions import MlflowException
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient

from inference.model_loader import load_native_model
from training.promotion_gate import evaluate_promotion_gate

matplotlib.use("Agg")

logger = logging.getLogger("routewise.training.mlflow_tracking")

LIFECYCLE_STAGES = ("Candidate", "Validated", "Production")


def build_lineage_tags(run_metadata: dict) -> dict:
    """Flat string-valued tags — MLflow tags must be strings. Together
    these make a run reproducible from the MLflow UI alone, without
    needing to separately dig through the repo's data/processed/ files.
    """
    dm = run_metadata["dataset_metadata"]
    tags = {
        "git_commit_sha": str(run_metadata.get("git_commit_sha")),
        "git_working_tree_dirty": str(run_metadata.get("git_working_tree_dirty")),
        "params_yaml_hash": str(run_metadata.get("params_yaml_hash")),
        "synthetic_data_yaml_hash": str(run_metadata.get("synthetic_data_yaml_hash")),
        "python_version": str(run_metadata.get("python_version")),
        "feature_manifest_schema_version": str(run_metadata.get("feature_manifest_schema_version")),
        "training_seed": str(run_metadata.get("training_seed")),
        "dataset_generation_seed": str(dm.get("generation_seed")),
        "dataset_version": str(dm.get("dataset_version")),
        "raw_schema_version": str(dm.get("raw_schema_version")),
        "feature_schema_version": str(dm.get("feature_schema_version")),
        "train_date_range": f"{dm['split_boundaries']['min_date']}..{dm['split_boundaries']['train_end']}",
        "val_date_range": f"{dm['split_boundaries']['train_end']}..{dm['split_boundaries']['val_end']}",
        "test_date_range": f"{dm['split_boundaries']['val_end']}..{dm['split_boundaries']['max_date']}",
        "train_row_count": str(dm["row_counts"]["train"]),
        "val_row_count": str(dm["row_counts"]["val"]),
        "test_row_count": str(dm["row_counts"]["test"]),
    }
    for dep, ver in run_metadata.get("dependency_versions", {}).items():
        tags[f"dependency_{dep.replace('-', '_')}"] = str(ver)
    for name, h in dm.get("dvc_raw_hashes", {}).items():
        tags[f"dvc_raw_hash_{name}"] = str(h)
    for name, h in run_metadata.get("processed_dvc_hashes", {}).items():
        tags[f"dvc_processed_hash_{name}"] = str(h)
    return tags


def build_run_params(model_label: str, model_type: str, params: dict, seed: int,
                      imbalance_decision: dict, threshold: float, dataset_version: str, config_version: str) -> dict:
    flat = {f"hp_{k}": v for k, v in params.items()}
    return {
        "model_label": model_label,
        "model_type": model_type,
        "random_seed": seed,
        "imbalance_strategy": imbalance_decision["strategy"],
        "scale_pos_weight_or_class_weight": str(imbalance_decision.get("scale_pos_weight")
                                                  or imbalance_decision.get("sklearn_class_weight")),
        "decision_threshold": threshold,
        "dataset_version": dataset_version,
        "config_version": config_version,
        **flat,
    }


def plot_confusion_matrix(cm: dict, title: str, out_path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(4, 4))
    matrix = np.array([[cm["tn"], cm["fp"]], [cm["fn"], cm["tp"]]])
    ax.imshow(matrix, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(matrix[i, j]), ha="center", va="center")
    ax.set_xticks([0, 1], ["Pred 0", "Pred 1"])
    ax.set_yticks([0, 1], ["True 0", "True 1"])
    ax.set_title(title)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def build_and_validate_signature(model, X_sample, predict_fn_name: str = "predict_proba"):
    """Infers a signature from a real inference call, then re-runs the
    same call to confirm the model actually produces output of the shape
    the signature claims — the "validate using a real inference example"
    requirement.
    """
    predict_fn = getattr(model, predict_fn_name)
    output = predict_fn(X_sample)
    if output.ndim == 2:
        output_for_signature = output[:, 1]  # positive-class probability, matches training/evaluate.py usage
    else:
        output_for_signature = output

    signature = infer_signature(X_sample, output_for_signature)

    assert output_for_signature.shape[0] == len(X_sample), (
        f"Signature validation: output length {output_for_signature.shape[0]} != input length {len(X_sample)}"
    )

    revalidation = predict_fn(X_sample)
    revalidation_col = revalidation[:, 1] if revalidation.ndim == 2 else revalidation
    assert revalidation_col.shape == output_for_signature.shape, "Signature validation: inference shape mismatch"
    assert np.all((revalidation_col >= 0) & (revalidation_col <= 1)), \
        "Signature validation: probability output out of [0,1] range"
    return signature, output_for_signature


def get_or_create_registered_model(client: MlflowClient, name: str, description: str | None = None):
    try:
        return client.get_registered_model(name)
    except MlflowException:
        return client.create_registered_model(name, description=description)


def set_lifecycle_stage(client: MlflowClient, name: str, version: str, stage: str) -> None:
    if stage not in LIFECYCLE_STAGES:
        raise ValueError(f"Unknown lifecycle stage '{stage}', must be one of {LIFECYCLE_STAGES}")
    client.set_model_version_tag(name, version, "lifecycle_stage", stage)


def get_production_test_metrics(client: MlflowClient, registered_model_name: str) -> dict | None:
    """Looks up the model version aliased "production", if any, and
    returns its logged test metrics from the run that produced it.
    Returns None if no production model has ever been promoted — the
    honest, expected state before any explicit promotion has happened.
    """
    try:
        mv = client.get_model_version_by_alias(registered_model_name, "production")
    except MlflowException:
        return None
    run = client.get_run(mv.run_id)
    metrics = {k.removeprefix("test_"): v for k, v in run.data.metrics.items() if k.startswith("test_")}
    return metrics or None


def log_and_register_model(
    *,
    model_label: str,
    model_type: str,
    model,
    flavor_log_fn,
    model_flavor: str,
    X_signature_sample,
    params: dict,
    val_metrics: dict,
    test_metrics: dict,
    run_metadata: dict,
    evaluation_payload: dict,
    feature_importance: dict,
    feature_manifest: dict,
    registered_model_name: str,
    gate_config: dict,
    artifacts_tmp_dir: Path,
) -> dict:
    """Logs one already-trained model (from Stage 4) as a proper MLflow
    run + registered model version. Returns a summary dict (run_id,
    model_version, gate_result) for the caller's final report.
    """
    tags = build_lineage_tags(run_metadata)
    run_params = build_run_params(
        model_label=model_label, model_type=model_type, params=params, seed=run_metadata["training_seed"],
        imbalance_decision=evaluation_payload["imbalance_decision"], threshold=evaluation_payload["decision_threshold"],
        dataset_version=run_metadata["dataset_metadata"]["dataset_version"],
        config_version=run_metadata["params_yaml_hash"],
    )

    signature, pre_log_predictions = build_and_validate_signature(model, X_signature_sample)

    with mlflow.start_run(run_name=f"{model_label}_stage5") as run:
        mlflow.set_tags(tags)
        mlflow.log_params(run_params)

        mlflow.log_metrics({f"val_{k}": v for k, v in val_metrics.items() if isinstance(v, int | float)})
        mlflow.log_metrics({f"test_{k}": v for k, v in test_metrics.items() if isinstance(v, int | float)})

        cm_path = plot_confusion_matrix(
            test_metrics["confusion_matrix"], f"{model_label} — test confusion matrix (threshold=0.5)",
            artifacts_tmp_dir / f"{model_label}_confusion_matrix_test.png",
        )
        mlflow.log_artifact(str(cm_path), artifact_path="evaluation")

        eval_path = artifacts_tmp_dir / f"{model_label}_evaluation.json"
        eval_path.write_text(json.dumps({"val_metrics": val_metrics, "test_metrics": test_metrics}, indent=2),
                              encoding="utf-8")
        mlflow.log_artifact(str(eval_path), artifact_path="evaluation")

        importance_path = artifacts_tmp_dir / f"{model_label}_feature_importance.json"
        importance_path.write_text(json.dumps(feature_importance, indent=2), encoding="utf-8")
        mlflow.log_artifact(str(importance_path), artifact_path="evaluation")

        manifest_path = artifacts_tmp_dir / "feature_manifest.json"
        if not manifest_path.exists():
            manifest_path.write_text(json.dumps(feature_manifest, indent=2), encoding="utf-8")
        mlflow.log_artifact(str(manifest_path), artifact_path="evaluation")

        model_meta = {
            "model_label": model_label, "model_type": model_type, "params": params,
            "training_time_seconds": evaluation_payload[model_type_key(model_type)]["training_time_seconds"],
            "feature_count": evaluation_payload[model_type_key(model_type)]["feature_count"],
        }
        meta_path = artifacts_tmp_dir / f"{model_label}_model_metadata.json"
        meta_path.write_text(json.dumps(model_meta, indent=2), encoding="utf-8")
        mlflow.log_artifact(str(meta_path), artifact_path="evaluation")

        model_info = flavor_log_fn(model, "model", signature=signature, input_example=X_signature_sample[:5])

        client = MlflowClient()
        get_or_create_registered_model(
            client, registered_model_name,
            description="RouteWise disruption-probability classifier (XGBoost primary / Random Forest baseline).",
        )
        mv = client.create_model_version(
            name=registered_model_name, source=model_info.model_uri, run_id=run.info.run_id,
        )
        client.set_model_version_tag(registered_model_name, mv.version, "model_flavor", model_flavor)
        set_lifecycle_stage(client, registered_model_name, mv.version, "Candidate")

        # Round-trip validation: reload the artifact that was just registered
        # (native flavor, via the SAME loader inference/model_loader.py will
        # use) and re-run real inference, proving the logged/registered
        # artifact itself works — not just the in-memory pre-log object.
        reloaded = load_native_model(f"models:/{registered_model_name}/{mv.version}", model_flavor)
        reloaded_predictions = reloaded.predict_proba(X_signature_sample)[:, 1]
        if not np.allclose(reloaded_predictions, pre_log_predictions, atol=1e-6):
            raise AssertionError(
                f"{model_label}: reloaded model predictions diverge from pre-log predictions — "
                "the registered artifact does not match what was validated."
            )
        mlflow.log_metric("signature_roundtrip_validated", 1)
        logger.info("%s: round-trip signature validation passed (reloaded predictions match pre-log)", model_label)

        production_metrics = get_production_test_metrics(client, registered_model_name)
        gate_result = evaluate_promotion_gate(test_metrics, production_metrics, gate_config)
        gate_path = artifacts_tmp_dir / f"{model_label}_promotion_gate.json"
        gate_path.write_text(json.dumps(gate_result.to_dict(), indent=2), encoding="utf-8")
        mlflow.log_artifact(str(gate_path), artifact_path="evaluation")
        mlflow.log_metric("promotion_gate_passed", int(gate_result.passed))

        if gate_result.passed:
            set_lifecycle_stage(client, registered_model_name, mv.version, "Validated")
            lifecycle_stage = "Validated"
        else:
            lifecycle_stage = "Candidate"

        logger.info("%s: registered as version %s, lifecycle_stage=%s, gate_passed=%s",
                    model_label, mv.version, lifecycle_stage, gate_result.passed)

        return {
            "run_id": run.info.run_id, "model_version": mv.version, "lifecycle_stage": lifecycle_stage,
            "gate_result": gate_result.to_dict(), "had_production_comparison": production_metrics is not None,
        }


def model_type_key(model_type: str) -> str:
    return {"xgboost": "xgboost", "random_forest": "random_forest"}[model_type]
