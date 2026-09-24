"""Stage 4 tests: schema/target verification, imbalance decision logic,
input preparation, evaluation metric correctness, and — where real trained
artifacts exist — model-loading and inference-shape checks. Model-training
integration tests are skipped if models/ hasn't been produced yet.
"""
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from training.data_loader import SchemaVerificationError, verify_schema, verify_temporal_ordering
from training.evaluate import compute_metrics, predicted_probability_distribution, threshold_sensitivity
from training.imbalance import compute_class_distribution, decide_imbalance_strategy
from training.prepare_inputs import ALL_FEATURES, build_xgboost_matrix, get_target

MANIFEST_MIN = {
    "features": [
        {"name": "a", "model_usage": "feature"},
        {"name": "record_id", "model_usage": "identifier"},
        {"name": "delay_minutes", "model_usage": "excluded (diagnostic only)"},
        {"name": "disruption_flag", "model_usage": "label"},
    ]
}


def _df(cols):
    return pd.DataFrame({c: [0, 1] for c in cols})


def test_verify_schema_passes_on_matching_columns():
    cols = ["a", "record_id", "delay_minutes", "disruption_flag"]
    df = _df(cols)
    verify_schema(df, df.copy(), df.copy(), MANIFEST_MIN)  # should not raise


def test_verify_schema_fails_on_missing_column():
    df = _df(["a", "record_id", "delay_minutes"])  # missing disruption_flag
    with pytest.raises(SchemaVerificationError):
        verify_schema(df, df.copy(), df.copy(), MANIFEST_MIN)


def test_verify_schema_fails_if_identifier_marked_as_feature():
    bad_manifest = {"features": [
        {"name": "record_id", "model_usage": "feature"},  # wrong on purpose
        {"name": "disruption_flag", "model_usage": "label"},
    ]}
    df = _df(["record_id", "disruption_flag"])
    with pytest.raises(SchemaVerificationError):
        verify_schema(df, df.copy(), df.copy(), bad_manifest)


def test_verify_schema_fails_if_diagnostic_marked_as_feature():
    bad_manifest = {"features": [
        {"name": "delay_minutes", "model_usage": "feature"},  # wrong on purpose
        {"name": "disruption_flag", "model_usage": "label"},
    ]}
    df = _df(["delay_minutes", "disruption_flag"])
    with pytest.raises(SchemaVerificationError):
        verify_schema(df, df.copy(), df.copy(), bad_manifest)


def test_verify_temporal_ordering_passes_for_disjoint_dates():
    train = pd.DataFrame({"service_date": [date(2025, 1, 1), date(2025, 1, 5)]})
    val = pd.DataFrame({"service_date": [date(2025, 1, 10)]})
    test = pd.DataFrame({"service_date": [date(2025, 1, 20)]})
    verify_temporal_ordering(train, val, test)  # should not raise


def test_verify_temporal_ordering_fails_on_overlap():
    train = pd.DataFrame({"service_date": [date(2025, 1, 1), date(2025, 1, 15)]})
    val = pd.DataFrame({"service_date": [date(2025, 1, 10)]})  # overlaps train's range
    test = pd.DataFrame({"service_date": [date(2025, 1, 20)]})
    with pytest.raises(SchemaVerificationError):
        verify_temporal_ordering(train, val, test)


def test_class_distribution_computation():
    y = pd.Series([0, 0, 0, 1])
    dist = compute_class_distribution(y)
    assert dist.n_total == 4
    assert dist.n_positive == 1
    assert dist.n_negative == 3
    assert dist.positive_rate == pytest.approx(0.25)
    assert dist.negative_to_positive_ratio == pytest.approx(3.0)


def test_imbalance_strategy_uses_train_ratio_only():
    dist = compute_class_distribution(pd.Series([0] * 80 + [1] * 20))  # ratio 4.0
    decision = decide_imbalance_strategy(dist, ratio_threshold=1.5)
    assert decision["strategy"] == "class_weighting"
    assert decision["scale_pos_weight"] == pytest.approx(4.0)
    assert decision["sklearn_class_weight"] == "balanced"


def test_imbalance_strategy_skips_weighting_below_threshold():
    dist = compute_class_distribution(pd.Series([0] * 55 + [1] * 45))  # ratio ~1.22
    decision = decide_imbalance_strategy(dist, ratio_threshold=1.5)
    assert decision["strategy"] == "none"
    assert decision["scale_pos_weight"] == 1.0


def test_build_xgboost_matrix_preserves_nan_and_sets_category_dtype():
    df = pd.DataFrame({c: [1.0, np.nan] for c in ALL_FEATURES})
    for cat_col in ["transport_mode", "day_period", "time_of_day_bucket"]:
        df[cat_col] = ["bus", None]
    X = build_xgboost_matrix(df)
    assert X["transport_mode"].dtype.name == "category"
    assert X["precipitation_mm"].isna().sum() == 1  # NaN preserved, not imputed


def test_get_target_casts_to_int():
    df = pd.DataFrame({"disruption_flag": [0.0, 1.0]})
    y = get_target(df)
    assert y.dtype == int
    assert list(y) == [0, 1]


def test_compute_metrics_probability_range_and_shape():
    y_true = np.array([0, 1, 0, 1, 1])
    y_prob = np.array([0.1, 0.9, 0.2, 0.6, 0.4])
    metrics = compute_metrics(y_true, y_prob, threshold=0.5)
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0
    assert 0.0 <= metrics["f1"] <= 1.0
    assert 0.0 <= metrics["roc_auc"] <= 1.0
    assert 0.0 <= metrics["pr_auc"] <= 1.0
    cm = metrics["confusion_matrix"]
    assert cm["tn"] + cm["fp"] + cm["fn"] + cm["tp"] == len(y_true)


def test_predicted_probability_distribution_bounds():
    y_prob = np.array([0.1, 0.5, 0.9])
    dist = predicted_probability_distribution(y_prob)
    assert dist["min"] == pytest.approx(0.1)
    assert dist["max"] == pytest.approx(0.9)


def test_threshold_sensitivity_returns_one_row_per_threshold():
    y_true = np.array([0, 1, 0, 1])
    y_prob = np.array([0.2, 0.8, 0.3, 0.7])
    rows = threshold_sensitivity(y_true, y_prob, thresholds=[0.3, 0.5, 0.7])
    assert len(rows) == 3
    assert all(0.0 <= r["precision"] <= 1.0 for r in rows)


# --- Integration tests against real trained artifacts (skipped if absent) ---

MODELS_DIR = Path("models")
ARTIFACTS_EXIST = (MODELS_DIR / "candidates" / "xgboost_tuned.joblib").exists()


@pytest.mark.skipif(not ARTIFACTS_EXIST, reason="Stage 4 models not trained yet")
def test_saved_models_load_and_predict_probability_shape_and_range():
    from src.preprocessing.pipeline import CATEGORICAL_FEATURES, NUMERIC_FEATURES

    xgb_model = joblib.load(MODELS_DIR / "candidates" / "xgboost_tuned.joblib")
    rf_model = joblib.load(MODELS_DIR / "candidates" / "random_forest_tuned.joblib")

    val_df = pd.read_parquet("data/processed/val.parquet").head(50)
    X_xgb = build_xgboost_matrix(val_df)
    xgb_prob = xgb_model.predict_proba(X_xgb)[:, 1]
    assert xgb_prob.shape == (50,)
    assert np.all((xgb_prob >= 0.0) & (xgb_prob <= 1.0))

    preprocessor = joblib.load("data/processed/preprocessor.joblib")
    X_rf = preprocessor.transform(val_df[NUMERIC_FEATURES + CATEGORICAL_FEATURES])
    rf_prob = rf_model.predict_proba(X_rf)[:, 1]
    assert rf_prob.shape == (50,)
    assert np.all((rf_prob >= 0.0) & (rf_prob <= 1.0))


@pytest.mark.skipif(not ARTIFACTS_EXIST, reason="Stage 4 models not trained yet")
def test_evaluation_json_has_val_and_test_sections_distinctly():
    import json
    payload = json.loads((MODELS_DIR / "evaluation" / "evaluation.json").read_text(encoding="utf-8"))
    for model_key in ["random_forest", "xgboost"]:
        assert "validation_metrics" in payload[model_key]
        assert "test_metrics" in payload[model_key]
        assert payload[model_key]["validation_metrics"]["confusion_matrix"] != {}
        assert payload[model_key]["test_metrics"]["confusion_matrix"] != {}
