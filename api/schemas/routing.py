"""Request/response schemas for POST /recommend-route and POST /reroute."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from api.schemas.common import ModelMetadataSchema


class SegmentSchema(BaseModel):
    edge_id: str = Field(description="Use this exact value as a key in POST /reroute's edge_updates.")
    from_stop: str
    to_stop: str
    route_id: str
    trip_id: str
    transport_mode: str
    travel_time: float
    cost: float
    disruption_probability: float = Field(ge=0.0, le=1.0)
    reliability: float = Field(ge=0.0, le=1.0)
    is_transfer_point: bool


class RouteSchema(BaseModel):
    route_id: str
    origin: str
    destination: str
    transport_modes: list[str]
    stops: list[str]
    segments: list[SegmentSchema]
    total_time: float
    total_cost: float
    reliability: float = Field(ge=0.0, le=1.0)
    disruption_risk: float = Field(ge=0.0, le=1.0)
    transfer_count: int = Field(ge=0)
    score: float
    decision_policy: str
    data_version: str | None
    explanation: str
    model_metadata: ModelMetadataSchema


class RouteRecommendationRequest(BaseModel):
    origin: str = Field(description="A stop_id from the current dataset.")
    destination: str = Field(description="A stop_id from the current dataset.")
    departure_time: datetime | None = Field(
        default=None, description="Defaults to routing.prediction_context.default_datetime if omitted."
    )
    top_n: int = Field(default=3, ge=1, le=10, description="Number of ranked candidates to return.")

    @field_validator("origin", "destination")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class RouteRecommendationResponse(BaseModel):
    origin: str
    destination: str
    candidates: list[RouteSchema]
    selected: RouteSchema = Field(description="candidates[0] — the top-ranked route.")


class RerouteRequest(BaseModel):
    origin: str
    destination: str
    edge_updates: dict[str, float] = Field(
        description="Map of edge_id -> new disruption_probability. Caller-supplied hypothetical update — "
                     "NOT connected to a live feed (see Stage 6 'adaptive rerouting capability').",
        min_length=1,
    )
    top_n: int = Field(default=3, ge=1, le=10)

    @field_validator("origin", "destination")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("edge_updates")
    @classmethod
    def _valid_probabilities(cls, v: dict[str, float]) -> dict[str, float]:
        for edge_id, p in v.items():
            if not 0.0 <= p <= 1.0:
                raise ValueError(f"disruption_probability for edge '{edge_id}' must be in [0,1], got {p}")
        return v


class RerouteResponse(BaseModel):
    data_source: str = Field(
        default="manual_update",
        description="Always 'manual_update' — this endpoint never claims to use a live data feed.",
    )
    original_route: RouteSchema
    updated_route: RouteSchema
    changed: bool
    old_risk: float = Field(ge=0.0, le=1.0)
    new_risk: float = Field(ge=0.0, le=1.0)
    old_score: float
    new_score: float
    reason: str
