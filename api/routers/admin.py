"""GET /admin/* — the internal engineering/MLOps API, kept separate from
the user-facing travel dashboard (see README "Internal admin view").
Never fabricates data: every endpoint reads a real artifact or the real
MLflow store, and returns an explicit unavailable state (never fake
rows) when that data doesn't exist.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_app_state
from api.exceptions import UnknownRunError
from api.schemas.admin import (
    DataSummaryResponse,
    EvaluationOverviewResponse,
    ExperimentsResponse,
    RegistryOverviewResponse,
    RunDetailResponse,
    TrainingStatusResponse,
)
from api.schemas.common import NOT_FOUND_RESPONSES
from api.services.admin_service import (
    build_data_summary,
    build_evaluation_overview,
    build_registry_overview,
    build_run_detail,
    build_training_status,
)
from api.services.system_service import build_experiments_overview
from api.state import AppState

router = APIRouter(tags=["admin"])


@router.get("/admin/experiments", response_model=ExperimentsResponse,
            summary="Real MLflow experiment run history (engineering view, not user-facing)")
async def admin_experiments(state: AppState = Depends(get_app_state)) -> ExperimentsResponse:
    return ExperimentsResponse(**build_experiments_overview(state.settings))


@router.get("/admin/training/status", response_model=TrainingStatusResponse,
            summary="Real training readiness and latest completed run (engineering view)")
async def admin_training_status() -> TrainingStatusResponse:
    return TrainingStatusResponse(**build_training_status())


@router.get("/admin/evaluation", response_model=EvaluationOverviewResponse,
            summary="Real saved evaluation artifacts — metrics, confusion matrix, feature importance")
async def admin_evaluation() -> EvaluationOverviewResponse:
    return EvaluationOverviewResponse(**build_evaluation_overview())


@router.get("/admin/data/summary", response_model=DataSummaryResponse,
            summary="Real ingested-dataset summary (engineering view)")
async def admin_data_summary() -> DataSummaryResponse:
    return DataSummaryResponse(**build_data_summary())


@router.get("/admin/registry", response_model=RegistryOverviewResponse,
            summary="Real MLflow Model Registry state — models, versions, lifecycle stages")
async def admin_registry(state: AppState = Depends(get_app_state)) -> RegistryOverviewResponse:
    return RegistryOverviewResponse(**build_registry_overview(state.settings))


@router.get("/admin/runs/{run_id}", response_model=RunDetailResponse, responses=NOT_FOUND_RESPONSES,
            summary="Full detail for one real MLflow run")
async def admin_run_detail(run_id: str, state: AppState = Depends(get_app_state)) -> RunDetailResponse:
    detail = build_run_detail(state.settings, run_id)
    if detail is None:
        raise UnknownRunError(run_id)
    return RunDetailResponse(**detail)
