from __future__ import annotations

from pydantic import BaseModel, Field


class OperationalLatency(BaseModel):
    mean: float | None
    p50: float | None
    p95: float | None
    max: float | None
    sample_size: int


class OperationalSnapshot(BaseModel):
    request_count: int
    successful_requests: int
    failed_requests: int
    prediction_errors: int
    route_recommendation_errors: int
    latency_ms: OperationalLatency
    model_load_status: str
    scope: str = Field(description="Local/development process-lifetime counters — reset on API restart, "
                                     "not distributed production monitoring.")


class MonitoringStatusResponse(BaseModel):
    available: bool = Field(description="Whether an offline monitoring run (src/monitoring/runner.py) has "
                                          "ever completed.")
    last_run_at: str | None
    dataset_type: str | None = Field(description="Always 'DEVELOPMENT/DEMO' when available — this project has "
                                                    "no production model or live traffic yet.")
    data_quality_status: str = Field(description="PASS | FAIL | NOT_RUN")
    data_drift_status: str = Field(description="NO_DRIFT | DRIFT_DETECTED | NOT_RUN")
    prediction_drift_status: str = Field(description="NO_DRIFT | DRIFT_DETECTED | NOT_RUN")
    performance_status: str = Field(description="OK | DEGRADED | NOT_AVAILABLE | NOT_RUN")
    decision: str = Field(description="NO_ACTION | REVIEW_REQUIRED | RETRAINING_RECOMMENDED | NOT_RUN — a "
                                        "deterministic signal, never an automatic retraining action.")
    operational: OperationalSnapshot


class SystemStatusResponse(BaseModel):
    application_version: str
    api_version: str
    model_name: str | None
    model_version: str | None
    model_lifecycle_stage: str | None
    is_production_model: bool
    production_model_available: bool = Field(description="Live registry check — is ANY version aliased 'production'.")
    configured_model_source: str = Field(description="'production' or 'candidate', from API config.")
    dataset_version: str | None
    feature_manifest_version: str | None
    routing_graph_available: bool
    routing_engine_version: str
    environment: str
    monitoring: MonitoringStatusResponse = Field(
        description="Stage 9 monitoring — the last offline run's result (NOT_RUN in every category if none has "
                     "ever completed) plus LIVE operational counters for this API process."
    )
    dvc_configured: bool = Field(description="Whether .dvc/ exists in the repo — a static repo-configuration check.")
    mlflow_reachable: bool = Field(description="Live check — could the API reach the MLflow tracking store.")
    ci_cd_configured: bool = Field(description="Whether .github/workflows/ci.yml exists — a static repo check.")
    risk_label_thresholds: dict = Field(
        description="params.yaml ui_risk_labels — moderate_threshold/high_threshold. UI display policy, "
                     "not a scientific or safety-certified classification. The frontend must read these "
                     "from here rather than hardcoding its own copy."
    )
