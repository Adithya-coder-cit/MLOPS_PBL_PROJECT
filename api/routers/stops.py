"""GET /stops — read-only stop listing (no ML/scoring). Available even
when the model failed to load, since it's static GTFS data."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_app_state
from api.schemas.stops import StopsResponse
from api.state import AppState

router = APIRouter(tags=["stops"])


@router.get("/stops", response_model=StopsResponse, summary="List all stops (for origin/destination selectors)")
async def list_stops(state: AppState = Depends(get_app_state)) -> StopsResponse:
    return StopsResponse(stops=state.stops)
