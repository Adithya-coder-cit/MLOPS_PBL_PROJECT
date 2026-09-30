"""API-level exceptions and their handlers. Every handler logs the full
detail server-side (logger.exception / logger.warning) and returns a
SAFE, structured message to the client — never a Python stack trace.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from inference.model_loader import NoProductionModelError
from src.routing.engine import UnreachableDestinationError
from src.routing.path_aggregation import InvalidPathError
from src.routing.path_search import NoPathFoundError

logger = logging.getLogger("routewise.api")


class UnknownStopError(Exception):
    def __init__(self, stop_id: str):
        self.stop_id = stop_id
        super().__init__(f"Unknown stop_id '{stop_id}'")


class UnknownRouteError(Exception):
    def __init__(self, route_id: str):
        self.route_id = route_id
        super().__init__(f"Unknown route_id '{route_id}'")


class UnknownRunError(Exception):
    """Raised by the admin API when a requested MLflow run_id doesn't exist in the tracking store."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"No MLflow run found with id '{run_id}'")


class ModelUnavailableError(Exception):
    """Raised when the configured prediction source could not be loaded
    at startup — inference endpoints must fail explicitly, not silently
    serve stale/absent predictions."""


class InferenceFailureError(Exception):
    """Raised when the model loaded successfully but a specific
    prediction call failed (e.g. malformed feature data reaching the
    model layer)."""


def _error_body(code: str, message: str, detail: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "detail": detail or {}}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        # exc.errors() can embed non-JSON-serializable objects (e.g. the raw
        # ValueError instance a custom @field_validator raised, under
        # ctx.error) — jsonable_encoder converts those to strings first.
        errors = jsonable_encoder(exc.errors(), exclude={"input"})
        logger.warning("Validation error on %s: %s", request.url.path, errors)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body("invalid_input", "Request validation failed", {"errors": errors}),
        )

    @app.exception_handler(UnknownStopError)
    async def unknown_stop_handler(request: Request, exc: UnknownStopError):
        logger.info("Unknown stop requested: %s", exc.stop_id)
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND,
                             content=_error_body("unknown_stop", str(exc), {"stop_id": exc.stop_id}))

    @app.exception_handler(UnknownRouteError)
    async def unknown_route_handler(request: Request, exc: UnknownRouteError):
        logger.info("Unknown route requested: %s", exc.route_id)
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND,
                             content=_error_body("unknown_route", str(exc), {"route_id": exc.route_id}))

    @app.exception_handler(UnknownRunError)
    async def unknown_run_handler(request: Request, exc: UnknownRunError):
        logger.info("Unknown MLflow run requested: %s", exc.run_id)
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND,
                             content=_error_body("unknown_run", str(exc), {"run_id": exc.run_id}))

    @app.exception_handler(UnreachableDestinationError)
    async def unreachable_handler(request: Request, exc: UnreachableDestinationError):
        logger.info("Unreachable destination: %s", exc)
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND,
                             content=_error_body("unreachable_destination", str(exc)))

    @app.exception_handler(NoPathFoundError)
    async def no_path_handler(request: Request, exc: NoPathFoundError):
        logger.info("No path found: %s", exc)
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND,
                             content=_error_body("no_path_found", str(exc)))

    @app.exception_handler(InvalidPathError)
    async def invalid_path_handler(request: Request, exc: InvalidPathError):
        logger.warning("Invalid route structure: %s", exc)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST,
                             content=_error_body("invalid_route", str(exc)))

    @app.exception_handler(ModelUnavailableError)
    async def model_unavailable_handler(request: Request, exc: ModelUnavailableError):
        logger.error("Model unavailable: %s", exc)
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                             content=_error_body("model_unavailable", str(exc)))

    @app.exception_handler(NoProductionModelError)
    async def no_production_model_handler(request: Request, exc: NoProductionModelError):
        logger.warning("No production model: %s", exc)
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                             content=_error_body("no_production_model", str(exc)))

    @app.exception_handler(InferenceFailureError)
    async def inference_failure_handler(request: Request, exc: InferenceFailureError):
        logger.exception("Inference failure")
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                             content=_error_body("inference_failure", "Model inference failed"))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s", request.url.path)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                             content=_error_body("internal_error", "An unexpected error occurred"))
