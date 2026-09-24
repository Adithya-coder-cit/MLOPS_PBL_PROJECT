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
