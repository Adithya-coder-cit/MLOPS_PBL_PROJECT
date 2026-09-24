"""GET /health — application availability only. Does NOT check the
model; a healthy API process can still have no usable model (see
GET /system/status and GET /model/info for that)."""
from __future__ import annotations

from fastapi import APIRouter

from api.config import APP_VERSION
from api.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Application liveness check")
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="routewise-api", version=APP_VERSION)
