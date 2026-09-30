"""Response schemas for the internal engineering/MLOps API (GET
/admin/*) — see README "Internal admin view". Every field here is read
from a real generated artifact or the real MLflow registry/tracking
store. Sections whose backing artifact doesn't exist return an explicit
unavailable state (available=False / a null field) rather than a
fabricated value.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExperimentRunSchema(BaseModel):
    run_id: str
    run_name: str | None
    model_type: str | None = Field(default=None, description="From the run's logged params, e.g. 'xgboost'.")
    status: str
    lifecycle_stage: str | None = Field(default=None, description="From the registered model version, if any.")
    registered_version: str | None
    start_time: str | None
    metrics: dict[str, float]


class ExperimentsResponse(BaseModel):
    available: bool
    reason: str | None = Field(default=None, description="Set when available=False — why real data isn't shown.")
    experiment_name: str
    mlflow_tracking_uri: str
    registered_model_name: str
    runs: list[ExperimentRunSchema]


# --- training status ---

class TrainedModelSummarySchema(BaseModel):
    model_type: str
    feature_count: int | None
    test_f1: float | None
    test_roc_auc: float | None
    registered_version: str | None
    run_id: str | None
    gate_passed: bool | None = Field(description="Result of the real Stage 5 promotion-gate check for this model.")


class LatestCompletedRunSchema(BaseModel):
    training_timestamp: str | None
    git_commit_sha: str | None
    dataset_label: str
    dataset_version: str | None
    train_records: int | None
    validation_records: int | None
    test_records: int | None
    models: list[TrainedModelSummarySchema]


class LatestRetrainingCheckSchema(BaseModel):
    timestamp: str | None
    dry_run: bool | None
    decision: str | None


class TrainingStatusResponse(BaseModel):
    real_data_model_ready: bool | None = Field(
        description="MODEL_READY from src/ingestion/model_readiness.py — whether the REAL (non-synthetic) "
                     "ingested dataset currently clears the bar for training on real data. None if that "
                     "artifact hasn't been generated."
    )
    real_data_model_ready_reason: str | None
    real_data_blocking_reasons: list[str]
    active_training_run: None = Field(
        default=None, description="Always null — this deployment has no live training-job tracker to report "
                                   "real progress from, so it never displays a fake one."
    )
    latest_completed_run: LatestCompletedRunSchema | None
    latest_retraining_check: LatestRetrainingCheckSchema | None


# --- evaluation ---

class EvaluationModelSchema(BaseModel):
    model_type: str
    validation_metrics: dict[str, float]
    test_metrics: dict[str, float]
    confusion_matrix: dict[str, int] | None
    threshold_sensitivity: list[dict] | None = Field(
        description="Real precision/recall/F1 at each of the 9 evaluated thresholds (0.1–0.9) — the only "
                     "PR-curve-like artifact actually saved; not a continuous curve."
    )
    feature_importance: list[dict] | None
    roc_curve_available: bool = Field(
        default=False, description="No fpr/tpr points were saved — only the scalar ROC-AUC."
    )
    pr_curve_available: bool = Field(
        default=False, description="Only discrete threshold_sensitivity points exist, not a continuous curve."
    )


class EvaluationOverviewResponse(BaseModel):
    available: bool
    reason: str | None = None
    selection_metric: str | None = None
    models: list[EvaluationModelSchema]
    comparison: list[dict]


# --- data summary ---

class DataSplitSchema(BaseModel):
    split: str
    records: int
    positive_rate: float | None
    modes: dict[str, int] = Field(default_factory=dict, description="Real mode_distribution for this split.")


class DataSummaryResponse(BaseModel):
    available: bool
    reason: str | None = None
    data_source: str
    total_real_records: int | None
    eligible_records: int | None
    excluded_records: int | None
    historical_feature_coverage: float | None
    weather_coverage: float | None
    weather_coverage_by_mode: dict[str, float]
    modes: list[str]
    splits: list[DataSplitSchema]
    dvc_configured: bool
    real_dataset_ready: bool | None


# --- model registry ---

class ModelVersionSchema(BaseModel):
    version: str
    lifecycle_stage: str
    is_production: bool
    test_f1: float | None
    test_roc_auc: float | None
    created: str | None
    run_id: str


class RegisteredModelSchema(BaseModel):
    name: str
    description: str | None
    latest_version: str | None
    latest_lifecycle_stage: str | None
    production_version: str | None
    created: str | None
    versions: list[ModelVersionSchema]


class RegistryOverviewResponse(BaseModel):
    available: bool
    reason: str | None = None
    total_models: int
    total_versions: int
    stage_counts: dict[str, int]
    models: list[RegisteredModelSchema]


# --- run detail ---

class RunDetailResponse(BaseModel):
    run_id: str
    run_name: str | None
    status: str
    start_time: str | None
    end_time: str | None
    params: dict[str, str]
    metrics: dict[str, float]
    tags: dict[str, str]
    registered_version: str | None
    lifecycle_stage: str | None
    artifact_paths: list[str] = Field(description="Relative artifact paths only — never a filesystem path.")
