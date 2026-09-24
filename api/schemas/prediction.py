"""Request/response schemas for POST /predict-disruption.

Field-level validation (types, ranges, formats) lives here in Pydantic.
Existence validation (does this stop_id/route_id actually exist in the
current dataset) happens in the service layer, since it needs the loaded
graph/raw-data context — Pydantic schemas don't have access to that.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import ModelMetadataSchema


class PredictionRequest(BaseModel):
    route_id: str = Field(description="A route_id from the current dataset, e.g. 'R005'.")
    stop_id: str = Field(description="The origin stop_id of the leg being predicted, e.g. 'S0021'.")
    query_datetime: datetime | None = Field(
        default=None, description="Defaults to routing.prediction_context.default_datetime if omitted."
    )
    precipitation_mm: float | None = Field(default=None, ge=0.0, le=500.0)
    temperature_c: float | None = Field(default=None, ge=-60.0, le=60.0)
    visibility_km: float | None = Field(default=None, ge=0.0, le=50.0)

    @field_validator("route_id", "stop_id")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class PredictionResponse(BaseModel):
    disruption_probability: float = Field(ge=0.0, le=1.0)
    predicted_class: int = Field(description="1 if disruption_probability >= the configured decision threshold.")
    decision_threshold: float
    feature_timestamp: datetime = Field(description="The query_datetime actually used (request value or default).")
    explanation: str
    top_factors: list[str] = Field(description="From the model's real, stored feature-importance ranking.")
    model_metadata: ModelMetadataSchema
