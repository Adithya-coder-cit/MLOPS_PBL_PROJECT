"""GET /model/info — full detail on the currently loaded model."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_app_state
from api.exceptions import ModelUnavailableError
from api.schemas.common import MODEL_UNAVAILABLE_RESPONSES
from api.schemas.model_info import ModelInfoResponse
from api.services.system_service import build_model_info
from api.state import AppState

router = APIRouter(tags=["model"])


@router.get("/model/info", response_model=ModelInfoResponse, responses=MODEL_UNAVAILABLE_RESPONSES,
            summary="Loaded model detail (validation vs. test kept separate)")
async def model_info(state: AppState = Depends(get_app_state)) -> ModelInfoResponse:
    if state.model_metadata is None:
        raise ModelUnavailableError(
            f"No model is currently loaded (configured source='{state.settings.model_source}'). "
            f"{state.model_load_error or ''}".strip()
        )
    return ModelInfoResponse(**build_model_info(state.model_metadata))
