"""POST /predict-disruption."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends

from api.dependencies import get_app_state, get_inference_service
from api.schemas.common import MODEL_UNAVAILABLE_RESPONSES, NOT_FOUND_RESPONSES
from api.schemas.prediction import PredictionRequest, PredictionResponse
from api.services.inference_service import InferenceService
from api.state import AppState

router = APIRouter(tags=["prediction"])


@router.post("/predict-disruption", response_model=PredictionResponse,
             responses={**NOT_FOUND_RESPONSES, **MODEL_UNAVAILABLE_RESPONSES},
             summary="Predict disruption probability for a route leg")
async def predict_disruption(
    body: PredictionRequest,
    service: InferenceService = Depends(get_inference_service),
    state: AppState = Depends(get_app_state),
) -> PredictionResponse:
    pc = state.params_config["routing"]["prediction_context"]
    default_weather = pc["default_weather"]
    query_datetime = body.query_datetime or datetime.fromisoformat(pc["default_datetime"])
    precipitation_mm = default_weather["precipitation_mm"] if body.precipitation_mm is None else body.precipitation_mm
    temperature_c = default_weather["temperature_c"] if body.temperature_c is None else body.temperature_c
    visibility_km = default_weather["visibility_km"] if body.visibility_km is None else body.visibility_km

    result = service.predict(body.route_id, body.stop_id, query_datetime, precipitation_mm, temperature_c,
                              visibility_km)

    metadata = state.model_metadata
    return PredictionResponse(
        disruption_probability=result.disruption_probability, predicted_class=result.predicted_class,
        decision_threshold=result.decision_threshold, feature_timestamp=result.feature_timestamp,
        explanation=result.explanation, top_factors=result.top_factors,
        model_metadata={
            "model_name": metadata.model_name, "model_version": metadata.model_version,
            "lifecycle_stage": metadata.lifecycle_stage,
            "is_production_model": metadata.lifecycle_stage == "Production",
            "model_source_warning": None if metadata.lifecycle_stage == "Production" else (
                "This prediction was made using a NON-PRODUCTION (candidate) model."
            ),
        },
    )
