from __future__ import annotations

from pydantic import BaseModel, Field


class ModelInfoResponse(BaseModel):
    model_name: str
    model_version: str
    model_type: str = Field(description="'xgboost' or 'sklearn' (Random Forest).")
    lifecycle_stage: str | None
    mlflow_run_id: str
    git_commit_sha: str | None
    dataset_version: str | None
    feature_manifest_version: str | None
    training_timestamp: str | None
    validation_metrics: dict = Field(description="Metrics from the VALIDATION split — used for model selection.")
    test_metrics: dict = Field(description="Metrics from the TEST split — evaluated once, after selection.")
    is_production_model: bool
