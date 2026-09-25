"""GET /system/status — factual system state, nothing fabricated."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_app_state
from api.schemas.system import SystemStatusResponse
from api.services.system_service import build_system_status
from api.state import AppState

router = APIRouter(tags=["system"])


@router.get("/system/status", response_model=SystemStatusResponse, summary="Factual system/model/graph status")
async def system_status(state: AppState = Depends(get_app_state)) -> SystemStatusResponse:
    status = build_system_status(
        state.settings, state.model_metadata, state.graph is not None, state.params_config,
        state.operational_metrics, state.model_available,
    )
    return SystemStatusResponse(**status)
