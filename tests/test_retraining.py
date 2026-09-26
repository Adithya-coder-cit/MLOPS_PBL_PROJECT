"""Stage 10 tests: retraining safety checks, the retrain.py orchestrator's
own decision logic (train.py/track_and_register.py/promotion_gate.py
internals are already covered by Stage 4/5 tests and are NOT re-tested
here), rollback, the monitoring->retraining trigger boundary, dry-run,
failure safety, idempotency, lineage, and CI workflow configuration.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import pytest
import yaml
from mlflow.tracking import MlflowClient
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier

from training import promote_model, retrain, retraining_safety, rollback, track_and_register, train
from training.mlflow_tracking import get_or_create_registered_model, log_and_register_model, set_lifecycle_stage
from training.retraining_safety import ERROR, WARNING, SafetyCheckError, SafetyIssue
from training.retraining_trigger import check_retraining_trigger

PROCESSED_ARTIFACTS_EXIST = Path("data/processed/train.parquet").exists()
requires_processed_data = pytest.mark.skipif(
    not PROCESSED_ARTIFACTS_EXIST, reason="Stage 3 processed dataset not generated yet"
)

SAMPLE_RUN_METADATA = {
    "training_timestamp": "2026-09-26T00:00:00",
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
    mlflow.set_experiment("stage10-test-experiment")
    return uri


def _fit_and_register(client: MlflowClient, model_name: str, X, y, lifecycle_stage: str,
                       with_signature_metric: bool = True) -> str:
    model = LogisticRegression().fit(X, y)
    with mlflow.start_run(run_name=f"register_{lifecycle_stage}") as run:
        model_info = mlflow.sklearn.log_model(model, "model")
        if with_signature_metric:
            mlflow.log_metric("signature_roundtrip_validated", 1)
        get_or_create_registered_model(client, model_name)
        mv = client.create_model_version(model_name, model_info.model_uri, run.info.run_id)
        client.set_model_version_tag(model_name, mv.version, "model_flavor", "sklearn")
        set_lifecycle_stage(client, model_name, mv.version, lifecycle_stage)
    return mv.version


# ============================== safety checks ==============================

class TestDatasetExists:
    def test_passes_when_all_files_present(self, tmp_path):
        for f in retraining_safety.REQUIRED_PROCESSED_FILES:
            (tmp_path / f).write_text("x", encoding="utf-8")
        assert retraining_safety.check_dataset_exists(tmp_path) == []

    def test_fails_with_missing_files_listed(self, tmp_path):
        issues = retraining_safety.check_dataset_exists(tmp_path)
        assert len(issues) == 1
        assert issues[0].level == ERROR
        assert "train.parquet" in issues[0].message


class TestConfigValid:
    def test_passes_with_all_required_sections(self):
        cfg = {s: {} for s in retraining_safety.REQUIRED_CONFIG_SECTIONS}
        cfg["training"]["seed"] = 42
        assert retraining_safety.check_config_valid(cfg) == []

    def test_fails_with_missing_sections(self):
        issues = retraining_safety.check_config_valid({"data": {}})
        assert len(issues) >= 1
        assert any("monitoring" in i.message for i in issues)

    def test_fails_when_training_seed_missing(self):
        cfg = {s: {} for s in retraining_safety.REQUIRED_CONFIG_SECTIONS}
        issues = retraining_safety.check_config_valid(cfg)
        assert any("seed" in i.message for i in issues)


class TestFeatureManifestSchema:
    def test_wraps_schema_verification_error_as_safety_issue(self, tmp_path, monkeypatch):
        def _raise(*_a, **_kw):
            raise retraining_safety.SchemaVerificationError("columns mismatch")
        monkeypatch.setattr(retraining_safety, "load_processed_datasets", _raise)
        issues = retraining_safety.check_feature_manifest_and_schema(tmp_path)
        assert len(issues) == 1
        assert issues[0].level == ERROR
        assert "columns mismatch" in issues[0].message

    def test_passes_when_load_succeeds(self, tmp_path, monkeypatch):
        monkeypatch.setattr(retraining_safety, "load_processed_datasets", lambda *_a, **_kw: object())
        assert retraining_safety.check_feature_manifest_and_schema(tmp_path) == []


class TestDependenciesCompatible:
    def test_passes_when_versions_match(self, tmp_path, monkeypatch):
        req = tmp_path / "requirements.txt"
        req.write_text("fakepkg==1.2.3\n", encoding="utf-8")
        monkeypatch.setattr(retraining_safety, "installed_version", lambda name: "1.2.3")
        issues = retraining_safety.check_dependencies_compatible(["fakepkg"], req)
        assert issues == []

    def test_fails_on_version_mismatch(self, tmp_path, monkeypatch):
        req = tmp_path / "requirements.txt"
        req.write_text("fakepkg==1.2.3\n", encoding="utf-8")
        monkeypatch.setattr(retraining_safety, "installed_version", lambda name: "9.9.9")
        issues = retraining_safety.check_dependencies_compatible(["fakepkg"], req)
        assert len(issues) == 1
        assert issues[0].level == ERROR

    def test_fails_when_package_not_installed(self, tmp_path, monkeypatch):
        req = tmp_path / "requirements.txt"
        req.write_text("fakepkg==1.2.3\n", encoding="utf-8")

        def _raise(name):
            raise retraining_safety.PackageNotFoundError(name)
        monkeypatch.setattr(retraining_safety, "installed_version", _raise)
        issues = retraining_safety.check_dependencies_compatible(["fakepkg"], req)
        assert len(issues) == 1
        assert "not installed" in issues[0].message

    def test_warns_when_requirements_file_missing(self, tmp_path):
        issues = retraining_safety.check_dependencies_compatible(["fakepkg"], tmp_path / "nope.txt")
        assert len(issues) == 1
        assert issues[0].level == WARNING


class TestDvcState:
    def test_passes_on_clean_status(self, monkeypatch):
        monkeypatch.setattr(Path, "exists", lambda self: True)
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(
            a, 0, stdout="Data and pipelines are up to date.\n", stderr=""))
        assert retraining_safety.check_dvc_state() == []

    def test_warns_on_dirty_status(self, monkeypatch):
        monkeypatch.setattr(Path, "exists", lambda self: True)
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(
            a, 0, stdout="modified: data/raw/gtfs\n", stderr=""))
        issues = retraining_safety.check_dvc_state()
        assert len(issues) == 1
        assert issues[0].level == WARNING

    def test_fails_when_dvc_status_exits_nonzero(self, monkeypatch):
        monkeypatch.setattr(Path, "exists", lambda self: True)
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(
            a, 1, stdout="", stderr="boom"))
        issues = retraining_safety.check_dvc_state()
        assert len(issues) == 1 and issues[0].level == ERROR

    def test_fails_when_not_initialized(self, monkeypatch):
        monkeypatch.setattr(Path, "exists", lambda self: False)
        issues = retraining_safety.check_dvc_state()
        assert len(issues) == 1 and "not initialized" in issues[0].message


class TestRaiseIfUnsafe:
    def test_no_errors_does_not_raise(self):
        retraining_safety.raise_if_unsafe([SafetyIssue(WARNING, "x", "just a warning")])

    def test_errors_raise_with_all_messages(self):
        issues = [SafetyIssue(ERROR, "a", "first"), SafetyIssue(ERROR, "b", "second")]
        with pytest.raises(SafetyCheckError, match="first"):
            retraining_safety.raise_if_unsafe(issues)


@requires_processed_data
def test_real_project_data_passes_all_safety_checks():
    params_config = yaml.safe_load(Path("params.yaml").read_text(encoding="utf-8"))
    issues = retraining_safety.run_safety_checks(params_config)
    errors = [i for i in issues if i.level == ERROR]
    assert errors == [], f"Unexpected safety errors on real project data: {errors}"


# ============================== retrain orchestration ==============================

def _fake_params_config(tmp_path) -> dict:
    return {
        "mlflow": {"tracking_uri": f"file:///{(tmp_path / 'mlruns').as_posix()}",
                   "registered_model_name": "stage10-orchestration-test-model"},
        "training": {"seed": 42, "selection_metric": "pr_auc"},
        "retraining": {"default_model_selection": "both", "default_promotion_mode": "manual"},
    }


def _write_minimal_processed_dir(tmp_path) -> Path:
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    (processed_dir / "dataset_metadata.json").write_text(json.dumps(SAMPLE_RUN_METADATA["dataset_metadata"]),
                                                           encoding="utf-8")
    (processed_dir / "feature_manifest.json").write_text(json.dumps({"schema_version": "1.0.0", "features": []}),
                                                           encoding="utf-8")
    return processed_dir


class TestRetrainOrchestration:
    def test_dry_run_never_calls_train_or_register(self, tmp_path, monkeypatch):
        monkeypatch.setattr(retrain, "RETRAINING_DIR", tmp_path / "retraining")
        monkeypatch.setattr(retrain, "LATEST_REPORT_PATH", tmp_path / "retraining" / "latest.json")
        monkeypatch.setattr(retrain, "run_safety_checks", lambda *a, **kw: [])
        called = {"train": False, "register": False}
        monkeypatch.setattr(train, "main", lambda *a, **kw: called.__setitem__("train", True))
        monkeypatch.setattr(track_and_register, "main", lambda *a, **kw: called.__setitem__("register", True))

        processed_dir = _write_minimal_processed_dir(tmp_path)
        result = retrain.retrain(
            params_config=_fake_params_config(tmp_path), dry_run=True, processed_dir=processed_dir,
        )
        assert result["decision"] == retrain.DECISION_DRY_RUN
        assert called == {"train": False, "register": False}
        assert result["plan"]["would_train"] == ["random_forest", "xgboost"]

    def test_unsafe_state_stops_before_training(self, tmp_path, monkeypatch):
        monkeypatch.setattr(retrain, "RETRAINING_DIR", tmp_path / "retraining")
        monkeypatch.setattr(retrain, "LATEST_REPORT_PATH", tmp_path / "retraining" / "latest.json")
        monkeypatch.setattr(retrain, "run_safety_checks",
                             lambda *a, **kw: [SafetyIssue(ERROR, "fake_check", "simulated failure")])
        called = {"train": False}
        monkeypatch.setattr(train, "main", lambda *a, **kw: called.__setitem__("train", True))

        processed_dir = _write_minimal_processed_dir(tmp_path)
        with pytest.raises(SafetyCheckError):
            retrain.retrain(params_config=_fake_params_config(tmp_path), processed_dir=processed_dir)
        assert called["train"] is False

        report = json.loads((tmp_path / "retraining" / "latest.json").read_text(encoding="utf-8"))
        assert report["decision"] == retrain.DECISION_REJECTED_UNSAFE

    def test_dataset_version_mismatch_refuses(self, tmp_path, monkeypatch):
        monkeypatch.setattr(retrain, "RETRAINING_DIR", tmp_path / "retraining")
        monkeypatch.setattr(retrain, "LATEST_REPORT_PATH", tmp_path / "retraining" / "latest.json")
        monkeypatch.setattr(retrain, "run_safety_checks", lambda *a, **kw: [])
        processed_dir = _write_minimal_processed_dir(tmp_path)
        with pytest.raises(retrain.RetrainRefused, match="does not match"):
            retrain.retrain(
                params_config=_fake_params_config(tmp_path), dataset_version="99.99.99", processed_dir=processed_dir,
            )

    def test_no_candidate_validated_when_gate_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(retrain, "RETRAINING_DIR", tmp_path / "retraining")
        monkeypatch.setattr(retrain, "LATEST_REPORT_PATH", tmp_path / "retraining" / "latest.json")
        monkeypatch.setattr(retrain, "run_safety_checks", lambda *a, **kw: [])
        monkeypatch.setattr(train, "main", lambda *a, **kw: {
            "random_forest": {"test_metrics": {"pr_auc": 0.1}},
            "xgboost": {"test_metrics": {"pr_auc": 0.1}},
        })
        monkeypatch.setattr(track_and_register, "main", lambda *a, **kw: {
            "random_forest": {"model_version": "1", "lifecycle_stage": "Candidate",
                               "gate_result": {"passed": False}},
            "xgboost": {"model_version": "2", "lifecycle_stage": "Candidate", "gate_result": {"passed": False}},
        })
        promote_called = {"called": False}
        monkeypatch.setattr(promote_model, "promote", lambda *a, **kw: promote_called.__setitem__("called", True))

        processed_dir = _write_minimal_processed_dir(tmp_path)
        result = retrain.retrain(params_config=_fake_params_config(tmp_path), processed_dir=processed_dir)
        assert result["decision"] == retrain.DECISION_TRAINED_NO_CANDIDATE_VALIDATED
        assert promote_called["called"] is False

    def test_validated_but_manual_mode_never_promotes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(retrain, "RETRAINING_DIR", tmp_path / "retraining")
        monkeypatch.setattr(retrain, "LATEST_REPORT_PATH", tmp_path / "retraining" / "latest.json")
        monkeypatch.setattr(retrain, "run_safety_checks", lambda *a, **kw: [])
        monkeypatch.setattr(train, "main", lambda *a, **kw: {
            "random_forest": {"test_metrics": {"pr_auc": 0.9}},
            "xgboost": {"test_metrics": {"pr_auc": 0.5}},
        })
        monkeypatch.setattr(track_and_register, "main", lambda *a, **kw: {
            "random_forest": {"model_version": "1", "lifecycle_stage": "Validated", "gate_result": {"passed": True}},
            "xgboost": {"model_version": "2", "lifecycle_stage": "Validated", "gate_result": {"passed": True}},
        })
        promote_called = {"called": False}
        monkeypatch.setattr(promote_model, "promote", lambda *a, **kw: promote_called.__setitem__("called", True))

        processed_dir = _write_minimal_processed_dir(tmp_path)
        result = retrain.retrain(
            params_config=_fake_params_config(tmp_path), promotion_mode="manual", processed_dir=processed_dir,
        )
        assert result["decision"] == retrain.DECISION_TRAINED_VALIDATED
        assert promote_called["called"] is False  # never promotes by default — Stage 10 §10

    def test_auto_mode_promotes_only_the_best_validated_candidate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(retrain, "RETRAINING_DIR", tmp_path / "retraining")
        monkeypatch.setattr(retrain, "LATEST_REPORT_PATH", tmp_path / "retraining" / "latest.json")
        monkeypatch.setattr(retrain, "run_safety_checks", lambda *a, **kw: [])
        monkeypatch.setattr(train, "main", lambda *a, **kw: {
            "random_forest": {"test_metrics": {"pr_auc": 0.9}},   # better — should be promoted
            "xgboost": {"test_metrics": {"pr_auc": 0.5}},
        })
        monkeypatch.setattr(track_and_register, "main", lambda *a, **kw: {
            "random_forest": {"model_version": "7", "lifecycle_stage": "Validated", "gate_result": {"passed": True}},
            "xgboost": {"model_version": "8", "lifecycle_stage": "Validated", "gate_result": {"passed": True}},
        })
        promoted = {}

        def _fake_promote(name, version, uri, confirm):
            promoted["name"], promoted["version"], promoted["confirm"] = name, version, confirm
        monkeypatch.setattr(promote_model, "promote", _fake_promote)

        processed_dir = _write_minimal_processed_dir(tmp_path)
        result = retrain.retrain(
            params_config=_fake_params_config(tmp_path), promotion_mode="auto", processed_dir=processed_dir,
        )
        assert result["decision"] == retrain.DECISION_TRAINED_PROMOTED
        assert promoted["version"] == "7"  # random_forest had the higher pr_auc
        assert promoted["confirm"] is True
        assert result["promoted"]["model_label"] == "random_forest"

    def test_report_contains_all_stage10_lineage_fields(self, tmp_path, monkeypatch):
        monkeypatch.setattr(retrain, "RETRAINING_DIR", tmp_path / "retraining")
        monkeypatch.setattr(retrain, "LATEST_REPORT_PATH", tmp_path / "retraining" / "latest.json")
        monkeypatch.setattr(retrain, "run_safety_checks", lambda *a, **kw: [])
        processed_dir = _write_minimal_processed_dir(tmp_path)
        result = retrain.retrain(params_config=_fake_params_config(tmp_path), dry_run=True, processed_dir=processed_dir)

        lineage = result["lineage"]
        for field in ["training_timestamp", "git_commit_sha", "params_yaml_hash", "python_version",
                      "dependency_versions", "feature_manifest_schema_version", "dataset_metadata",
                      "processed_dvc_hashes"]:
            assert field in lineage, f"missing required Stage 10 §4 lineage field: {field}"
        assert "dvc_raw_hashes" in lineage["dataset_metadata"]

    def test_idempotent_dry_run_produces_equivalent_plan_twice(self, tmp_path, monkeypatch):
        monkeypatch.setattr(retrain, "RETRAINING_DIR", tmp_path / "retraining")
        monkeypatch.setattr(retrain, "LATEST_REPORT_PATH", tmp_path / "retraining" / "latest.json")
        monkeypatch.setattr(retrain, "run_safety_checks", lambda *a, **kw: [])
        processed_dir = _write_minimal_processed_dir(tmp_path)
        cfg = _fake_params_config(tmp_path)
        r1 = retrain.retrain(params_config=cfg, dry_run=True, processed_dir=processed_dir)
        r2 = retrain.retrain(params_config=cfg, dry_run=True, processed_dir=processed_dir)
        assert r1["decision"] == r2["decision"] == retrain.DECISION_DRY_RUN
        assert r1["plan"] == r2["plan"]
        assert r1["production_before"] == r2["production_before"]

    def test_rejects_unknown_model_choice(self, tmp_path):
        with pytest.raises(ValueError):
            retrain.retrain(params_config=_fake_params_config(tmp_path), model="not-a-real-model")

    def test_rejects_unknown_promotion_mode(self, tmp_path):
        with pytest.raises(ValueError):
            retrain.retrain(params_config=_fake_params_config(tmp_path), promotion_mode="not-a-real-mode")


@requires_processed_data
def test_real_dry_run_against_real_project_artifacts():
    """Stage 10 §21-style smoke test using ACTUAL project artifacts —
    proves the dry-run path works end to end without training."""
    result = retrain.retrain(dry_run=True)
    assert result["decision"] == retrain.DECISION_DRY_RUN
    assert "would_train" in result["plan"]
    assert result["safety_checks"] == [] or all(i["level"] != ERROR for i in result["safety_checks"])


# ============================== idempotency (model level) ==============================

def test_same_seed_same_data_produces_equivalent_xgboost_predictions():
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"a": rng.normal(0, 1, 300), "b": rng.normal(0, 1, 300)})
    y = (X["a"] + X["b"] > 0).astype(int)

    m1 = XGBClassifier(n_estimators=20, max_depth=3, random_state=42).fit(X, y)
    m2 = XGBClassifier(n_estimators=20, max_depth=3, random_state=42).fit(X, y)

    p1 = m1.predict_proba(X)[:, 1]
    p2 = m2.predict_proba(X)[:, 1]
    assert np.allclose(p1, p2, atol=1e-6)


# ============================== rollback ==============================

class TestRollback:
    def test_refuses_nonexistent_version(self, tmp_tracking):
        client = MlflowClient()
        get_or_create_registered_model(client, "rollback-missing-version-model")
        with pytest.raises(rollback.RollbackRefused, match="does not exist"):
            rollback.rollback("rollback-missing-version-model", "999", tmp_tracking, confirm=True)

    def test_refuses_candidate_only_version(self, tmp_tracking):
        client = MlflowClient()
        X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
        y = [0, 0, 1, 1]
        version = _fit_and_register(client, "rollback-candidate-only-model", X, y, "Candidate")
        with pytest.raises(rollback.RollbackRefused, match="eligible for rollback"):
            rollback.rollback("rollback-candidate-only-model", version, tmp_tracking, confirm=True)

    def test_refuses_without_signature_validation_metric(self, tmp_tracking):
        client = MlflowClient()
        X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
        y = [0, 0, 1, 1]
        version = _fit_and_register(client, "rollback-no-sig-model", X, y, "Validated",
                                     with_signature_metric=False)
        with pytest.raises(rollback.RollbackRefused, match="signature_roundtrip_validated"):
            rollback.rollback("rollback-no-sig-model", version, tmp_tracking, confirm=True)

    def test_dry_run_does_not_change_alias(self, tmp_tracking):
        client = MlflowClient()
        X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
        y = [0, 0, 1, 1]
        version = _fit_and_register(client, "rollback-dry-run-model", X, y, "Validated")
        plan = rollback.rollback("rollback-dry-run-model", version, tmp_tracking, dry_run=True)
        assert plan["executed"] is False
        with pytest.raises(Exception):  # noqa: B017 - no alias was ever set
            client.get_model_version_by_alias("rollback-dry-run-model", "production")

    def test_without_confirm_does_not_execute(self, tmp_tracking):
        client = MlflowClient()
        X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
        y = [0, 0, 1, 1]
        version = _fit_and_register(client, "rollback-no-confirm-model", X, y, "Validated")
        plan = rollback.rollback("rollback-no-confirm-model", version, tmp_tracking, confirm=False)
        assert plan["executed"] is False

    def test_confirmed_rollback_sets_alias_and_records_event(self, tmp_tracking):
        client = MlflowClient()
        X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
        y = [0, 0, 1, 1]
        version = _fit_and_register(client, "rollback-confirmed-model", X, y, "Validated")

        plan = rollback.rollback("rollback-confirmed-model", version, tmp_tracking, confirm=True)
        assert plan["executed"] is True
        assert plan["was_real_production_rollback"] is False  # no prior production existed

        mv = client.get_model_version_by_alias("rollback-confirmed-model", "production")
        assert mv.version == version
        assert (mv.tags or {}).get("lifecycle_stage") == "Production"

    def test_rollback_between_two_real_production_versions(self, tmp_tracking):
        client = MlflowClient()
        X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
        y = [0, 0, 1, 1]
        v1 = _fit_and_register(client, "rollback-two-versions-model", X, y, "Validated")
        v2 = _fit_and_register(client, "rollback-two-versions-model", X, y, "Validated")

        rollback.rollback("rollback-two-versions-model", v1, tmp_tracking, confirm=True)
        assert client.get_model_version_by_alias("rollback-two-versions-model", "production").version == v1

        plan = rollback.rollback("rollback-two-versions-model", v2, tmp_tracking, confirm=True)
        assert plan["from_version"] == v1
        assert plan["to_version"] == v2
        assert plan["was_real_production_rollback"] is True
        assert client.get_model_version_by_alias("rollback-two-versions-model", "production").version == v2

        # Neither version was deleted.
        assert client.get_model_version("rollback-two-versions-model", v1) is not None
        assert client.get_model_version("rollback-two-versions-model", v2) is not None


# ============================== promotion gate reuse (no duplicated criteria) ==============================

class TestPromotionGateReuse:
    def test_failing_gate_keeps_candidate_and_never_sets_validated(self, tmp_tracking, tmp_path):
        X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0], "b": [0.1, 0.2, 0.3, 0.4, 0.5]})
        y = [0, 0, 1, 1, 0]
        model = LogisticRegression().fit(X, y)
        low_metrics = {"pr_auc": 0.01, "recall": 0.01, "precision": 0.01, "f1": 0.01, "roc_auc": 0.01,
                        "confusion_matrix": {"tn": 1, "fp": 1, "fn": 1, "tp": 1}}
        summary = log_and_register_model(
            model_label="stage10_failing", model_type="xgboost", model=model,
            flavor_log_fn=mlflow.sklearn.log_model, model_flavor="sklearn", X_signature_sample=X,
            params={"n": 1}, val_metrics=low_metrics, test_metrics=low_metrics,
            run_metadata=SAMPLE_RUN_METADATA,
            evaluation_payload={"imbalance_decision": {"strategy": "none"}, "decision_threshold": 0.5,
                                 "xgboost": {"training_time_seconds": 0.1, "feature_count": 2}},
            feature_importance={}, feature_manifest={"schema_version": "1.0.0"},
            registered_model_name="stage10-gate-fail-model", gate_config=GATE_CONFIG, artifacts_tmp_dir=tmp_path,
        )
        assert summary["gate_result"]["passed"] is False
        assert summary["lifecycle_stage"] == "Candidate"

    def test_passing_gate_sets_validated_not_production(self, tmp_tracking, tmp_path):
        X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0], "b": [0.1, 0.2, 0.3, 0.4, 0.5]})
        y = [0, 0, 1, 1, 0]
        model = LogisticRegression().fit(X, y)
        high_metrics = {"pr_auc": 0.9, "recall": 0.9, "precision": 0.9, "f1": 0.9, "roc_auc": 0.9,
                         "confusion_matrix": {"tn": 1, "fp": 1, "fn": 1, "tp": 1}}
        summary = log_and_register_model(
            model_label="stage10_passing", model_type="xgboost", model=model,
            flavor_log_fn=mlflow.sklearn.log_model, model_flavor="sklearn", X_signature_sample=X,
            params={"n": 1}, val_metrics=high_metrics, test_metrics=high_metrics,
            run_metadata=SAMPLE_RUN_METADATA,
            evaluation_payload={"imbalance_decision": {"strategy": "none"}, "decision_threshold": 0.5,
                                 "xgboost": {"training_time_seconds": 0.1, "feature_count": 2}},
            feature_importance={}, feature_manifest={"schema_version": "1.0.0"},
            registered_model_name="stage10-gate-pass-model", gate_config=GATE_CONFIG, artifacts_tmp_dir=tmp_path,
        )
        assert summary["gate_result"]["passed"] is True
        assert summary["lifecycle_stage"] == "Validated"

        client = MlflowClient()
        with pytest.raises(Exception):  # noqa: B017 - passing the gate must NOT itself set production
            client.get_model_version_by_alias("stage10-gate-pass-model", "production")


# ============================== monitoring -> retraining trigger boundary ==============================

class TestRetrainingTrigger:
    def test_no_report_means_not_recommended(self, monkeypatch):
        from training import retraining_trigger
        monkeypatch.setattr(retraining_trigger, "read_latest_report", lambda: None)
        result = check_retraining_trigger()
        assert result["retraining_recommended"] is False
        assert result["decision"] == "NOT_RUN"

    def test_review_required_is_not_a_retraining_trigger(self):
        result = check_retraining_trigger(report={"decision": "REVIEW_REQUIRED", "decision_reasons": ["drift"]})
        assert result["retraining_recommended"] is False

    def test_retraining_recommended_is_detected(self):
        result = check_retraining_trigger(
            report={"decision": "RETRAINING_RECOMMENDED", "decision_reasons": ["performance regression"],
                     "monitoring_timestamp": "2026-01-01T00:00:00"},
        )
        assert result["retraining_recommended"] is True
        assert result["reasons"] == ["performance regression"]

    def test_never_shells_out(self):
        """The trigger check must be pure — no subprocess/os.system calls
        anywhere in the module (Stage 10 §17: not allowed to execute
        arbitrary shell commands)."""
        import inspect

        from training import retraining_trigger
        source = inspect.getsource(retraining_trigger)
        assert "subprocess" not in source
        assert "os.system" not in source


# ============================== CI workflow configuration ==============================

WORKFLOWS_DIR = Path(".github/workflows")
SECRET_PATTERNS = [r"AKIA[0-9A-Z]{16}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"]


class TestCIWorkflowConfiguration:
    @pytest.mark.parametrize("workflow_file", sorted(WORKFLOWS_DIR.glob("*.yml")) if WORKFLOWS_DIR.exists() else [])
    def test_workflow_parses_as_valid_yaml_with_jobs(self, workflow_file):
        doc = yaml.safe_load(workflow_file.read_text(encoding="utf-8"))
        assert "jobs" in doc
        assert len(doc["jobs"]) > 0

    @pytest.mark.parametrize("workflow_file", sorted(WORKFLOWS_DIR.glob("*.yml")) if WORKFLOWS_DIR.exists() else [])
    def test_workflow_has_no_hardcoded_secret_patterns(self, workflow_file):
        import re
        text = workflow_file.read_text(encoding="utf-8")
        for pattern in SECRET_PATTERNS:
            assert not re.search(pattern, text), f"Possible hardcoded secret matching {pattern} in {workflow_file}"

    def test_all_expected_workflows_exist(self):
        for name in ["ci.yml", "monitoring.yml", "retraining.yml"]:
            assert (WORKFLOWS_DIR / name).exists(), f"Missing workflow: {name}"

    def test_retraining_workflow_supports_dry_run_input(self):
        doc = yaml.safe_load((WORKFLOWS_DIR / "retraining.yml").read_text(encoding="utf-8"))
        # PyYAML parses the unquoted GitHub Actions key `on:` as the
        # boolean True per YAML 1.1 — a well-known gotcha, not a bug here.
        on_section = doc.get("on", doc.get(True))
        dispatch_inputs = on_section["workflow_dispatch"]["inputs"]
        assert "dry_run" in dispatch_inputs
        assert "model_selection" in dispatch_inputs
        assert "promotion_mode" in dispatch_inputs

    def test_ci_workflow_does_not_invoke_full_training(self):
        text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")
        assert "python -m training.train" not in text
        assert "python -m training.retrain" not in text
