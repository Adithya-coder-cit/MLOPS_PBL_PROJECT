"""FastAPI dependencies — thin accessors into the AppState built once at
startup (api/startup.py). Endpoint functions depend on these rather than
reaching into app.state directly, and raise a clear, typed error when
the model/graph isn't available instead of letting a None slip through.
"""
from __future__ import annotations

from fastapi import Request

from api.exceptions import ModelUnavailableError
from api.services.inference_service import InferenceService
from api.services.routing_service import RoutingService
from api.state import AppState


def get_app_state(request: Request) -> AppState:
    return request.app.state.routewise


def get_inference_service(request: Request) -> InferenceService:
    state = get_app_state(request)
    if state.inference_service is None:
        raise ModelUnavailableError(
            f"No model is available for inference (configured source='{state.settings.model_source}'). "
            f"{state.model_load_error or ''}".strip()
        )
    return state.inference_service


def get_routing_service(request: Request) -> RoutingService:
    state = get_app_state(request)
    if state.routing_service is None:
        raise ModelUnavailableError(
            f"The routing graph is unavailable because no model could be loaded "
            f"(configured source='{state.settings.model_source}'). {state.model_load_error or ''}".strip()
        )
    return state.routing_service
