"""Stage 9 monitoring tests: data quality, data drift, prediction drift,
performance, threshold configuration, decision logic, reference/current
dataset lineage, no-label behavior, deterministic controlled drift
scenarios, and monitoring status behavior. Unit-level checks use small
synthetic DataFrames (fast, no dependency on the real processed
dataset); a few integration checks run the full runner against the real
Stage 3 artifacts and are skipped if those aren't present.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src.monitoring import data_drift, data_quality, decision, performance, prediction_drift, reference, scenarios
from src.monitoring.operational import OperationalMetrics
from src.monitoring.schemas import (
    DEGRADED,
    DRIFT_DETECTED,
    FAIL,
    NO_ACTION,
    NO_DRIFT,
    NOT_AVAILABLE,
    OK,
    PASS,
    RETRAINING_RECOMMENDED,
    REVIEW_REQUIRED,
)
from tests.conftest import mlflow_candidate_available

PROCESSED_ARTIFACTS_EXIST = Path("data/processed/train.parquet").exists()
requires_processed_data = pytest.mark.skipif(
    not PROCESSED_ARTIFACTS_EXIST, reason="Stage 3 processed dataset not generated yet"
)

# Running the real monitoring runner additionally needs an actual
# registered MLflow candidate to score — data existing is not enough
# (e.g. ci.yml generates data but never trains/registers a model).
requires_registered_model = pytest.mark.skipif(
    not PROCESSED_ARTIFACTS_EXIST or not mlflow_candidate_available(),
    reason="Stage 3 processed dataset not generated, or no registered MLflow candidate model available",
)


def _params_config() -> dict:
    return yaml.safe_load(Path("params.yaml").read_text(encoding="utf-8"))


# --- fixtures: small synthetic frames for fast unit tests ---

def _quality_config() -> dict:
    return {"max_missing_share": 0.05, "range_tolerance_std": 3.0}


def _drift_config() -> dict:
    return {
        "numerical_stattest": "ks", "numerical_threshold": 0.05,
        "categorical_stattest": "psi", "categorical_threshold": 0.1,
        "dataset_drift_share": 0.5,
    }


def _pred_drift_config() -> dict:
    return {"probability_stattest": "ks", "probability_threshold": 0.05, "class_stattest": "psi",
            "class_threshold": 0.1}


def _synthetic_frame(n: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "record_id": [f"R{i}" for i in range(n)],
        "num_a": rng.normal(0, 1, n),
        "cat_a": rng.choice(["x", "y", "z"], n, p=[0.7, 0.2, 0.1]),
    })


# --- data quality ---

class TestDataQuality:
    def test_clean_batch_passes(self):
        ref = _synthetic_frame(seed=1)
        cur = _synthetic_frame(seed=2)
        issues = data_quality.check_ranges_vs_reference(ref, cur, ["num_a"], tolerance_std=3.0)
        assert issues == []
        assert data_quality.data_quality_status([]) == PASS

    def test_missing_values_above_threshold_flag_error(self):
        ref = _synthetic_frame(seed=1)
        cur = _synthetic_frame(seed=2)
        cur.loc[: int(len(cur) * 0.5), "num_a"] = None  # 50% missing, way above 5%
        issues, raw = data_quality.run_missing_values_check(ref, cur, ["num_a", "cat_a"], max_missing_share=0.05)
        assert any(i.check == "missing_values" and i.level == "ERROR" for i in issues)
        assert data_quality.data_quality_status(issues) == FAIL
        assert raw["share_of_missing_values_by_column"]["num_a"] > 0.4

    def test_missing_values_below_threshold_do_not_flag(self):
        ref = _synthetic_frame(seed=1)
        cur = _synthetic_frame(seed=2)
        cur.loc[0, "num_a"] = None  # ~0.3%, below 5%
        issues, _raw = data_quality.run_missing_values_check(ref, cur, ["num_a", "cat_a"], max_missing_share=0.05)
        assert issues == []

    def test_schema_change_flags_missing_column(self):
        cur = _synthetic_frame(seed=2).drop(columns=["num_a"])
        issues = data_quality.check_schema(cur, ["num_a", "cat_a"])
        assert len(issues) == 1
        assert issues[0].check == "schema_change"
        assert issues[0].level == "ERROR"

    def test_new_categorical_value_is_flagged(self):
        ref = _synthetic_frame(seed=1)
        cur = _synthetic_frame(seed=2)
        cur.loc[0, "cat_a"] = "brand_new_category"
        issues = data_quality.check_categorical_new_values(ref, cur, ["cat_a"])
        assert len(issues) == 1
        assert "brand_new_category" in issues[0].message

    def test_range_violation_beyond_reference_is_flagged(self):
        ref = _synthetic_frame(seed=1)
        cur = _synthetic_frame(seed=2)
        cur.loc[0, "num_a"] = ref["num_a"].max() + 100 * ref["num_a"].std()
        issues = data_quality.check_ranges_vs_reference(ref, cur, ["num_a"], tolerance_std=3.0)
        assert len(issues) == 1
        assert issues[0].check == "range_vs_reference"

    def test_duplicate_records_are_flagged(self):
        cur = _synthetic_frame(seed=2)
        cur.loc[1, "record_id"] = cur.loc[0, "record_id"]
        issues = data_quality.check_duplicates(cur, key_column="record_id")
        assert len(issues) == 1
        assert issues[0].level == "ERROR"

    def test_no_duplicate_key_column_is_a_noop(self):
        cur = _synthetic_frame(seed=2).drop(columns=["record_id"])
        assert data_quality.check_duplicates(cur, key_column="record_id") == []


# --- data drift ---

class TestDataDrift:
    def test_split_feature_types_uses_actual_dtypes(self):
        df = _synthetic_frame()
        numeric, categorical = data_drift.split_feature_types(df, ["num_a", "cat_a"])
        assert numeric == ["num_a"]
        assert categorical == ["cat_a"]

    def test_identical_reference_and_current_shows_no_drift(self):
        ref = _synthetic_frame(seed=42)
        cur = scenarios.scenario_a_identical(ref)
        result = data_drift.run_feature_drift(ref, cur, ["num_a", "cat_a"], _drift_config())
        assert result["dataset_drift_detected"] is False
        assert data_drift.feature_drift_status(result) == NO_DRIFT
        assert all(not v["drift_detected"] for v in result["per_feature"].values())

    def test_controlled_feature_shift_is_detected(self):
        ref = _synthetic_frame(seed=42, n=500)
        cur = scenarios.scenario_b_feature_shift(_synthetic_frame(seed=43, n=500), "num_a", shift_std_multiples=6.0)
        result = data_drift.run_feature_drift(ref, cur, ["num_a", "cat_a"], _drift_config())
        assert result["per_feature"]["num_a"]["drift_detected"] is True
        assert data_drift.feature_drift_status(result) == DRIFT_DETECTED

    def test_html_report_is_written_when_path_given(self, tmp_path):
        ref = _synthetic_frame(seed=1)
        cur = _synthetic_frame(seed=2)
        html_path = tmp_path / "report.html"
        data_drift.run_feature_drift(ref, cur, ["num_a", "cat_a"], _drift_config(), html_path=html_path)
        assert html_path.exists()
        assert html_path.stat().st_size > 0


# --- prediction drift ---

class TestPredictionDrift:
    def test_identical_probabilities_show_no_drift(self):
        rng = np.random.default_rng(0)
        prob = rng.uniform(0, 1, 500)
        result = prediction_drift.run_prediction_drift(prob, prob.copy(), _pred_drift_config())
        assert prediction_drift.prediction_drift_status(result) == NO_DRIFT

    def test_controlled_prediction_shift_is_detected(self):
        rng = np.random.default_rng(0)
        ref_prob = rng.uniform(0, 0.5, 500)
        cur_prob = scenarios.scenario_c_prediction_shift(ref_prob.copy(), shift=0.4)
        result = prediction_drift.run_prediction_drift(ref_prob, cur_prob, _pred_drift_config())
        assert result["predicted_probability_drift"]["drift_detected"] is True
        assert prediction_drift.prediction_drift_status(result) == DRIFT_DETECTED

    def test_prediction_drift_is_distinct_from_feature_drift(self):
        # Same reference/current FEATURE frame (no feature drift at all), but
        # a deliberately shifted prediction distribution — Stage 9 §11: the
        # two must be reported/decided on independently.
        ref_features = _synthetic_frame(seed=1)
        cur_features = scenarios.scenario_a_identical(ref_features)
        feature_result = data_drift.run_feature_drift(ref_features, cur_features, ["num_a", "cat_a"], _drift_config())
        assert data_drift.feature_drift_status(feature_result) == NO_DRIFT

        rng = np.random.default_rng(1)
        ref_prob = rng.uniform(0, 0.5, 500)
        cur_prob = scenarios.scenario_c_prediction_shift(ref_prob.copy(), shift=0.4)
        pred_result = prediction_drift.run_prediction_drift(ref_prob, cur_prob, _pred_drift_config())
        assert prediction_drift.prediction_drift_status(pred_result) == DRIFT_DETECTED


# --- performance ---

class TestPerformance:
    def test_no_labels_reports_explicit_unavailable_message(self):
        result = performance.run_performance_monitoring(
            None, None, baseline_metrics={"pr_auc": 0.5}, regression_tolerance={"pr_auc": 0.05},
        )
        assert result["available"] is False
        assert result["message"] == performance.LABEL_UNAVAILABLE_MESSAGE
        assert performance.performance_status(result) == NOT_AVAILABLE

    def test_matching_distribution_is_not_a_regression(self):
        rng = np.random.default_rng(0)
        y_true = rng.integers(0, 2, 1000)
        y_prob = np.clip(y_true * 0.6 + rng.normal(0, 0.2, 1000), 0, 1)
        # Use the SAME data as its own baseline: current==baseline, so no metric should regress.
        from training.evaluate import compute_metrics
        baseline_metrics = compute_metrics(y_true, y_prob)
        result = performance.run_performance_monitoring(
            y_true, y_prob, baseline_metrics=baseline_metrics,
            regression_tolerance={"pr_auc": 0.05, "recall": 0.05, "precision": 0.05, "f1": 0.05, "roc_auc": 0.05},
        )
        assert result["available"] is True
        assert performance.performance_status(result) == OK
        assert all(not r["regressed"] for r in result["regressions"].values())

    def test_controlled_performance_degradation_is_detected(self):
        rng = np.random.default_rng(7)
        y_true = rng.integers(0, 2, 2000)
        y_prob = np.clip(y_true * 0.7 + rng.normal(0, 0.15, 2000), 0, 1)
        from training.evaluate import compute_metrics
        baseline_metrics = compute_metrics(y_true, y_prob)

        degraded_prob = scenarios.scenario_d_performance_degradation(y_prob, degrade_fraction=0.6)
        result = performance.run_performance_monitoring(
            y_true, degraded_prob, baseline_metrics=baseline_metrics,
            regression_tolerance={"pr_auc": 0.05, "recall": 0.05, "precision": 0.05, "f1": 0.05, "roc_auc": 0.05},
        )
        assert performance.performance_status(result) == DEGRADED
        assert any(r["regressed"] for r in result["regressions"].values())

    def test_missing_baseline_metric_is_skipped_not_fabricated(self):
        y_true = np.array([0, 1, 0, 1, 1])
        y_prob = np.array([0.1, 0.8, 0.2, 0.9, 0.6])
        result = performance.run_performance_monitoring(
            y_true, y_prob, baseline_metrics={}, regression_tolerance={"pr_auc": 0.05},
        )
        assert result["regressions"] == {}
        assert performance.performance_status(result) == OK


# --- decision policy ---

class TestDecisionPolicy:
    FULL_POLICY = {
        "review_required_if_data_quality_fail": True,
        "review_required_if_data_drift_detected": True,
        "review_required_if_prediction_drift_detected": True,
        "retraining_recommended_if_performance_degraded": True,
    }

    def test_no_action_when_everything_clean(self):
        result, reasons = decision.decide(PASS, NO_DRIFT, NO_DRIFT, OK, self.FULL_POLICY)
        assert result == NO_ACTION
        assert reasons

    def test_drift_alone_never_escalates_to_retraining(self):
        result, _reasons = decision.decide(PASS, DRIFT_DETECTED, DRIFT_DETECTED, OK, self.FULL_POLICY)
        assert result == REVIEW_REQUIRED

    def test_data_quality_failure_triggers_review(self):
        result, reasons = decision.decide(FAIL, NO_DRIFT, NO_DRIFT, OK, self.FULL_POLICY)
        assert result == REVIEW_REQUIRED
        assert any("quality" in r.lower() for r in reasons)

    def test_performance_degradation_triggers_retraining_recommended(self):
        result, reasons = decision.decide(PASS, NO_DRIFT, NO_DRIFT, DEGRADED, self.FULL_POLICY)
        assert result == RETRAINING_RECOMMENDED
        assert any("performance" in r.lower() for r in reasons)

    def test_performance_degradation_takes_priority_over_drift_reasons(self):
        result, reasons = decision.decide(FAIL, DRIFT_DETECTED, DRIFT_DETECTED, DEGRADED, self.FULL_POLICY)
        assert result == RETRAINING_RECOMMENDED
        assert len(reasons) == 1  # short-circuits — doesn't also report drift/quality reasons

    def test_policy_toggle_disables_a_trigger(self):
        policy = dict(self.FULL_POLICY, review_required_if_data_drift_detected=False)
        result, _reasons = decision.decide(PASS, DRIFT_DETECTED, NO_DRIFT, OK, policy)
        assert result == NO_ACTION

    def test_policy_toggle_disables_retraining_trigger(self):
        policy = dict(self.FULL_POLICY, retraining_recommended_if_performance_degraded=False)
        result, _reasons = decision.decide(PASS, NO_DRIFT, NO_DRIFT, DEGRADED, policy)
        assert result == NO_ACTION


# --- reference/current dataset lineage ---

class TestReferenceLineage:
    def test_split_period_reads_actual_boundaries_not_hardcoded(self):
        dataset_metadata = {"split_boundaries": {
            "min_date": "2025-01-01", "train_end": "2025-02-01", "val_end": "2025-02-15", "max_date": "2025-03-01",
        }}
        assert reference.split_period(dataset_metadata, "train") == {"start": "2025-01-01", "end": "2025-02-01"}
        assert reference.split_period(dataset_metadata, "val") == {"start": "2025-02-01", "end": "2025-02-15"}
        assert reference.split_period(dataset_metadata, "test") == {"start": "2025-02-15", "end": "2025-03-01"}

    def test_split_period_rejects_unknown_split(self):
        with pytest.raises(ValueError):
            reference.split_period({"split_boundaries": {}}, "bogus")

    def test_establish_reference_writes_metadata(self, tmp_path, monkeypatch):
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        (processed_dir / "dataset_metadata.json").write_text(
            '{"dataset_version": "9.9.9", "split_boundaries": '
            '{"min_date": "2025-01-01", "train_end": "2025-02-01", "val_end": "2025-02-15", "max_date": "2025-03-01"}}',
            encoding="utf-8",
        )
        (processed_dir / "feature_manifest.json").write_text('{"schema_version": "1.0.0"}', encoding="utf-8")
        monitoring_dir = tmp_path / "monitoring"
        monkeypatch.setattr(reference, "MONITORING_DIR", monitoring_dir)
        monkeypatch.setattr(reference, "REFERENCE_METADATA_PATH", monitoring_dir / "reference_metadata.json")

        meta = reference.establish_or_verify_reference("train", "M", "1", "sha123", processed_dir=processed_dir)
        assert meta["dataset_version"] == "9.9.9"
        assert meta["model_version"] == "1"
        assert reference.REFERENCE_METADATA_PATH.exists()

    def test_reference_change_without_force_raises(self, tmp_path, monkeypatch):
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        (processed_dir / "dataset_metadata.json").write_text(
            '{"dataset_version": "1.0.0", "split_boundaries": '
            '{"min_date": "2025-01-01", "train_end": "2025-02-01", "val_end": "2025-02-15", "max_date": "2025-03-01"}}',
            encoding="utf-8",
        )
        (processed_dir / "feature_manifest.json").write_text('{"schema_version": "1.0.0"}', encoding="utf-8")
        monitoring_dir = tmp_path / "monitoring"
        monkeypatch.setattr(reference, "MONITORING_DIR", monitoring_dir)
        monkeypatch.setattr(reference, "REFERENCE_METADATA_PATH", monitoring_dir / "reference_metadata.json")
        reference.establish_or_verify_reference("train", "M", "1", "sha123", processed_dir=processed_dir)

        # Now the dataset version "changes" underneath the same reference split.
        (processed_dir / "dataset_metadata.json").write_text(
            '{"dataset_version": "2.0.0", "split_boundaries": '
            '{"min_date": "2025-01-01", "train_end": "2025-02-01", "val_end": "2025-02-15", "max_date": "2025-03-01"}}',
            encoding="utf-8",
        )
        with pytest.raises(reference.ReferenceChangedError):
            reference.establish_or_verify_reference("train", "M", "1", "sha123", processed_dir=processed_dir)

        # force=True intentionally re-establishes it.
        meta = reference.establish_or_verify_reference(
            "train", "M", "1", "sha123", processed_dir=processed_dir, force=True,
        )
        assert meta["dataset_version"] == "2.0.0"


# --- controlled scenarios (Stage 9 §14) determinism ---

class TestControlledScenarios:
    def test_scenario_a_is_a_deep_copy_not_the_same_object(self):
        ref = _synthetic_frame()
        cur = scenarios.scenario_a_identical(ref)
        pd.testing.assert_frame_equal(ref, cur)
        assert cur is not ref

    def test_scenario_b_is_deterministic(self):
        cur = _synthetic_frame(seed=2)
        out1 = scenarios.scenario_b_feature_shift(cur, "num_a", 4.0)
        out2 = scenarios.scenario_b_feature_shift(cur, "num_a", 4.0)
        pd.testing.assert_frame_equal(out1, out2)

    def test_scenario_c_is_deterministic_and_bounded(self):
        prob = np.array([0.1, 0.5, 0.9])
        out1 = scenarios.scenario_c_prediction_shift(prob, 0.4)
        out2 = scenarios.scenario_c_prediction_shift(prob, 0.4)
        np.testing.assert_array_equal(out1, out2)
        assert out1.max() <= 1.0 and out1.min() >= 0.0

    def test_scenario_d_is_deterministic_across_runs(self):
        prob = np.linspace(0.05, 0.95, 200)
        out1 = scenarios.scenario_d_performance_degradation(prob, 0.5)
        out2 = scenarios.scenario_d_performance_degradation(prob, 0.5)
        np.testing.assert_array_equal(out1, out2)

    def test_scenario_functions_never_mutate_their_input(self):
        ref = _synthetic_frame(seed=5)
        ref_copy = ref.copy(deep=True)
        scenarios.scenario_a_identical(ref)
        scenarios.scenario_b_feature_shift(ref, "num_a", 2.0)
        pd.testing.assert_frame_equal(ref, ref_copy)

        prob = np.array([0.2, 0.4, 0.6])
        prob_copy = prob.copy()
        scenarios.scenario_c_prediction_shift(prob, 0.3)
        scenarios.scenario_d_performance_degradation(prob, 0.5)
        np.testing.assert_array_equal(prob, prob_copy)


# --- operational monitoring ---

class TestOperationalMetrics:
    def test_snapshot_starts_at_zero(self):
        metrics = OperationalMetrics()
        snap = metrics.snapshot(model_available=True)
        assert snap["request_count"] == 0
        assert snap["model_load_status"] == "available"
        assert snap["latency_ms"]["sample_size"] == 0

    def test_records_success_and_failure(self):
        metrics = OperationalMetrics()
        metrics.record_request("/api/v1/health", 200, 5.0)
        metrics.record_request("/api/v1/predict-disruption", 422, 3.0)
        snap = metrics.snapshot(model_available=False)
        assert snap["request_count"] == 2
        assert snap["successful_requests"] == 1
        assert snap["failed_requests"] == 1
        assert snap["prediction_errors"] == 1
        assert snap["model_load_status"] == "unavailable"

    def test_classifies_route_recommendation_errors(self):
        metrics = OperationalMetrics()
        metrics.record_request("/api/v1/recommend-route", 503, 10.0)
        metrics.record_request("/api/v1/reroute", 503, 10.0)
        snap = metrics.snapshot(model_available=False)
        assert snap["route_recommendation_errors"] == 2
        assert snap["prediction_errors"] == 0

    def test_latency_summary_reports_percentiles(self):
        metrics = OperationalMetrics()
        for ms in [1, 2, 3, 4, 5]:
            metrics.record_request("/api/v1/health", 200, float(ms))
        snap = metrics.snapshot(model_available=True)
        assert snap["latency_ms"]["sample_size"] == 5
        assert snap["latency_ms"]["max"] == 5.0
        assert snap["latency_ms"]["mean"] == 3.0


# --- full runner integration (requires real Stage 3 artifacts) ---

@requires_registered_model
class TestRunnerIntegration:
    def test_end_to_end_run_produces_a_sane_result(self):
        from src.monitoring.runner import run_monitoring

        params_config = _params_config()
        params_config["monitoring"]["monitored_features"] = ["precipitation_mm", "transport_mode", "hour"]
        result = run_monitoring(
            params_config=params_config, model_source="candidate", candidate_version="4",
        )
        assert result.dataset_type == "DEVELOPMENT/DEMO"
        assert result.model_name == "RouteWise-Disruption-Model"
        assert result.data_quality_status in {PASS, FAIL}
        assert result.data_drift_status in {NO_DRIFT, DRIFT_DETECTED}
        assert result.prediction_drift_status in {NO_DRIFT, DRIFT_DETECTED}
        assert result.performance_status in {OK, DEGRADED, NOT_AVAILABLE}
        assert result.decision in {NO_ACTION, REVIEW_REQUIRED, RETRAINING_RECOMMENDED}

    def test_refuses_batch_below_minimum_size(self, monkeypatch):
        from src.monitoring import runner as runner_module

        params_config = _params_config()
        params_config["monitoring"]["minimum_batch_size"] = 10_000_000
        with pytest.raises(ValueError, match="minimum_batch_size"):
            runner_module.run_monitoring(params_config=params_config, model_source="candidate", candidate_version="4")

    def test_reproducible_across_two_runs(self):
        from src.monitoring.runner import run_monitoring

        params_config = _params_config()
        params_config["monitoring"]["monitored_features"] = ["precipitation_mm", "transport_mode", "hour"]
        result1 = run_monitoring(params_config=params_config, model_source="candidate", candidate_version="4")
        result2 = run_monitoring(params_config=params_config, model_source="candidate", candidate_version="4")

        assert result1.data_quality_status == result2.data_quality_status
        assert result1.data_drift_status == result2.data_drift_status
        assert result1.prediction_drift_status == result2.prediction_drift_status
        assert result1.performance_status == result2.performance_status
        assert result1.decision == result2.decision
        assert result1.data_drift["share_of_drifted_columns"] == result2.data_drift["share_of_drifted_columns"]
        if result1.performance["available"]:
            assert result1.performance["current_metrics"]["pr_auc"] == result2.performance["current_metrics"]["pr_auc"]
