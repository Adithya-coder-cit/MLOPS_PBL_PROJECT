"""Read-only stop listing — no ML/scoring logic. Exists so the frontend
never hardcodes a stop list that could drift from the real dataset."""
from __future__ import annotations

from pydantic import BaseModel, Field


class StopSchema(BaseModel):
    stop_id: str
    stop_name: str
    lat: float
    lon: float
    zone_id: str
    has_scheduled_service: bool = Field(
        default=True,
        description="Computed from the real routing graph's node degree at startup — false means this "
                    "stop has zero scheduled trips in the current dataset (a genuine GTFS data gap, not "
                    "a routing bug) and can never be a reachable origin/destination. True (the default) "
                    "when the routing graph itself is unavailable, since route search is disabled "
                    "entirely in that case and this flag is moot.",
    )


class StopsResponse(BaseModel):
    stops: list[StopSchema]


class NetworkRouteSchema(BaseModel):
    route_id: str
    direction_id: int
    transport_mode: str
    stop_ids: list[str] = Field(
        description="The real, ordered stop sequence for one representative trip of this "
                    "route+direction — the same representative-trip selection the routing "
                    "graph itself is built from (src.routing.graph_builder), never invented.",
    )


class NetworkRoutesResponse(BaseModel):
    routes: list[NetworkRouteSchema]
