"""Stage 5 tests: MLflow run creation, required params/metrics, artifact
existence, model signature, model loading, promotion gate, and metadata
generation. Uses an isolated temporary MLflow tracking store (tmp_path) —
never touches the project's real ./mlruns.
"""
import numpy as np
import pandas as pd
import pytest

pytest.importorskip("mlflow")

import mlflow  # noqa: E402
from mlflow.tracking import MlflowClient  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402

from inference.model_loader import (  # noqa: E402
    NoProductionModelError,
    load_model_version,
    load_native_model,
    load_production_model,
)
from training.mlflow_tracking import (  # noqa: E402
    build_and_validate_signature,
    build_lineage_tags,
    build_run_params,
    get_or_create_registered_model,
    get_production_test_metrics,
    plot_confusion_matrix,
    set_lifecycle_stage,
)
from training.promotion_gate import evaluate_promotion_gate  # noqa: E402

SAMPLE_RUN_METADATA = {
    "git_commit_sha": "abc123",
    "git_working_tree_dirty": False,
    "params_yaml_hash": "hash1",
    "synthetic_data_yaml_hash": "hash2",
    "python_version": "3.11.5",
    "feature_manifest_schema_version": "1.0.0",
    "training_seed": 42,
    "dependency_versions": {"xgboost": "2.1.1", "scikit-learn": "1.7.2"},
    "processed_dvc_hashes": {"train_parquet": "dvc1", "val_parquet": "dvc2"},
    "dataset_metadata": {
        "generation_seed": 42, "dataset_version": "0.1.0",
        "raw_schema_version": "1.0.0", "feature_schema_version": "1.0.0",
        "dvc_raw_hashes": {"gtfs": "gtfs_hash"},
        "split_boundaries": {"min_date": "2025-06-01", "train_end": "2025-08-23",
                              "val_end": "2025-09-10", "max_date": "2025-09-28"},
        "row_counts": {"train": 100, "val": 20, "test": 20},
    },
}

GATE_CONFIG = {
    "minimum_thresholds": {"min_pr_auc": 0.3, "min_recall": 0.4, "min_precision": 0.3, "min_f1": 0.4,
                            "min_roc_auc": 0.6},
    "regression_tolerance": {"pr_auc": 0.02, "recall": 0.02, "precision": 0.02, "f1": 0.02, "roc_auc": 0.02},
}


@pytest.fixture
def tmp_tracking(tmp_path, monkeypatch):
    uri = f"file:///{(tmp_path / 'mlruns').as_posix()}"
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment("stage5-test-experiment")
    return uri


# --- lineage / params ---

def test_build_lineage_tags_are_all_strings():
    tags = build_lineage_tags(SAMPLE_RUN_METADATA)
    assert all(isinstance(v, str) for v in tags.values())
    assert tags["git_commit_sha"] == "abc123"
    assert tags["dvc_raw_hash_gtfs"] == "gtfs_hash"
    assert tags["dvc_processed_hash_train_parquet"] == "dvc1"
    assert tags["train_row_count"] == "100"


def test_build_run_params_includes_required_fields():
    params = build_run_params(
        model_label="xgboost", model_type="xgboost", params={"n_estimators": 200, "max_depth": 4},
        seed=42, imbalance_decision={"strategy": "class_weighting", "scale_pos_weight": 2.7},
        threshold=0.5, dataset_version="0.1.0", config_version="hash1",
    )
    for key in ["model_label", "model_type", "random_seed", "imbalance_strategy", "decision_threshold",
                "dataset_version", "config_version", "hp_n_estimators", "hp_max_depth"]:
        assert key in params


# --- MLflow run creation, required params/metrics, artifacts ---

def test_mlflow_run_creation_with_required_params_and_metrics(tmp_tracking, tmp_path):
    with mlflow.start_run(run_name="test_run") as run:
        mlflow.set_tags(build_lineage_tags(SAMPLE_RUN_METADATA))
        mlflow.log_params(build_run_params(
            "xgboost", "xgboost", {"n_estimators": 10}, 42,
            {"strategy": "none", "scale_pos_weight": 1.0}, 0.5, "0.1.0", "hash1",
        ))
        mlflow.log_metrics({"val_f1": 0.5, "test_f1": 0.51})
        cm_path = plot_confusion_matrix({"tn": 10, "fp": 2, "fn": 3, "tp": 5}, "test cm", tmp_path / "cm.png")
        mlflow.log_artifact(str(cm_path), artifact_path="evaluation")

    client = MlflowClient()
    fetched = client.get_run(run.info.run_id)
    assert fetched.data.params["model_type"] == "xgboost"
    assert fetched.data.metrics["val_f1"] == pytest.approx(0.5)
    assert fetched.data.metrics["test_f1"] == pytest.approx(0.51)
    assert fetched.data.tags["git_commit_sha"] == "abc123"

    artifacts = [a.path for a in client.list_artifacts(run.info.run_id, "evaluation")]
    assert any("cm.png" in a for a in artifacts)


def test_val_and_test_metrics_are_never_the_same_key(tmp_tracking):
    with mlflow.start_run(run_name="test_run_2") as run:
        mlflow.log_metrics({"val_precision": 0.4, "test_precision": 0.45})
    client = MlflowClient()
    fetched = client.get_run(run.info.run_id)
    assert fetched.data.metrics["val_precision"] != fetched.data.metrics["test_precision"]


# --- signature ---

def test_signature_describes_names_types_and_output(tmp_tracking):
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [0.1, 0.2, 0.3, 0.4]})
    y = [0, 0, 1, 1]
    model = LogisticRegression().fit(X, y)
    signature, predictions = build_and_validate_signature(model, X)
    input_names = [inp.name for inp in signature.inputs.inputs]
    assert set(input_names) == {"a", "b"}
    assert signature.outputs is not None
    assert predictions.shape == (4,)
    assert np.all((predictions >= 0) & (predictions <= 1))


def test_signature_validation_catches_bad_predict_fn(tmp_tracking):
    class BrokenModel:
        def predict_proba(self, X):
            return np.array([[0.9, 0.1]])  # wrong length vs input

    X = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    with pytest.raises(Exception):  # noqa: B017 - broad on purpose, any failure proves validation isn't a no-op
        build_and_validate_signature(BrokenModel(), X)


# --- model loading ---

def test_load_native_model_rejects_unknown_flavor():
    with pytest.raises(ValueError):
        load_native_model("models:/fake/1", "not-a-real-flavor")


def test_registry_round_trip_load_and_predict(tmp_tracking):
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [0.1, 0.2, 0.3, 0.4]})
    y = [0, 0, 1, 1]
    model = LogisticRegression().fit(X, y)

    with mlflow.start_run(run_name="registry_test") as run:
        model_info = mlflow.sklearn.log_model(model, "model")
        client = MlflowClient()
        get_or_create_registered_model(client, "test-registered-model")
        mv = client.create_model_version("test-registered-model", model_info.model_uri, run.info.run_id)
        client.set_model_version_tag("test-registered-model", mv.version, "model_flavor", "sklearn")
        set_lifecycle_stage(client, "test-registered-model", mv.version, "Candidate")

    loaded, metadata = load_model_version(mv.version, model_name="test-registered-model")
    assert np.allclose(loaded.predict_proba(X)[:, 1], model.predict_proba(X)[:, 1])
    assert metadata.model_flavor == "sklearn"
    assert metadata.lifecycle_stage == "Candidate"
    assert metadata.run_id == run.info.run_id


def test_load_production_model_raises_when_no_alias_set(tmp_tracking):
    client = MlflowClient()
    get_or_create_registered_model(client, "no-production-yet-model")
    with pytest.raises(NoProductionModelError):
        load_production_model(model_name="no-production-yet-model")


# --- promotion gate ---

def test_promotion_gate_passes_when_all_thresholds_cleared():
    candidate = {"pr_auc": 0.5, "recall": 0.6, "precision": 0.5, "f1": 0.55, "roc_auc": 0.7}
    result = evaluate_promotion_gate(candidate, None, GATE_CONFIG)
    assert result.passed is True


def test_promotion_gate_fails_below_minimum_threshold():
    candidate = {"pr_auc": 0.1, "recall": 0.6, "precision": 0.5, "f1": 0.55, "roc_auc": 0.7}
    result = evaluate_promotion_gate(candidate, None, GATE_CONFIG)
    assert result.passed is False
    failed = [c for c in result.checks if not c.passed]
    assert any(c.metric == "pr_auc" for c in failed)


def test_promotion_gate_regression_tolerance_against_production():
    candidate = {"pr_auc": 0.45, "recall": 0.6, "precision": 0.5, "f1": 0.55, "roc_auc": 0.7}
    production = {"pr_auc": 0.50, "recall": 0.6, "precision": 0.5, "f1": 0.55, "roc_auc": 0.7}  # 0.05 regression
    result = evaluate_promotion_gate(candidate, production, GATE_CONFIG)
    assert result.passed is False  # 0.05 > 0.02 tolerance on pr_auc
    regression_checks = [c for c in result.checks if c.check_type == "regression_tolerance"]
    assert any(c.metric == "pr_auc" and not c.passed for c in regression_checks)


def test_promotion_gate_no_production_skips_regression_checks():
    candidate = {"pr_auc": 0.5, "recall": 0.6, "precision": 0.5, "f1": 0.55, "roc_auc": 0.7}
    result = evaluate_promotion_gate(candidate, None, GATE_CONFIG)
    assert all(c.check_type == "minimum_threshold" for c in result.checks)


def test_get_production_test_metrics_returns_none_when_absent(tmp_tracking):
    client = MlflowClient()
    get_or_create_registered_model(client, "no-prod-metrics-model")
    assert get_production_test_metrics(client, "no-prod-metrics-model") is None
