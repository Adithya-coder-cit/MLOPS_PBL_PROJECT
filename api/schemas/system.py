from __future__ import annotations

from pydantic import BaseModel, Field


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
    monitoring_status: str = Field(description="Evidently/drift monitoring is not implemented yet (Stage 8+).")
    dvc_configured: bool = Field(description="Whether .dvc/ exists in the repo — a static repo-configuration check.")
    mlflow_reachable: bool = Field(description="Live check — could the API reach the MLflow tracking store.")
    ci_cd_configured: bool = Field(description="Whether .github/workflows/ci.yml exists — a static repo check.")
    risk_label_thresholds: dict = Field(
        description="params.yaml ui_risk_labels — moderate_threshold/high_threshold. UI display policy, "
                     "not a scientific or safety-certified classification. The frontend must read these "
                     "from here rather than hardcoding its own copy."
    )
