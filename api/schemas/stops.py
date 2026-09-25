"""Read-only stop listing — no ML/scoring logic. Exists so the frontend
never hardcodes a stop list that could drift from the real dataset."""
from __future__ import annotations

from pydantic import BaseModel


class StopSchema(BaseModel):
    stop_id: str
    stop_name: str
    lat: float
    lon: float
    zone_id: str


class StopsResponse(BaseModel):
    stops: list[StopSchema]
