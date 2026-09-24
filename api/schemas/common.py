"""Shared response building blocks."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ModelMetadataSchema(BaseModel):
    model_name: str
    model_version: str
    lifecycle_stage: str | None = Field(description="'Candidate', 'Validated', or 'Production' — never implied.")
    is_production_model: bool
    model_source_warning: str | None = Field(
        default=None, description="Present whenever a non-production model was used for this response."
    )


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


NOT_FOUND_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Unknown stop/route, or destination unreachable from origin."},
}
MODEL_UNAVAILABLE_RESPONSES = {
    503: {"model": ErrorResponse, "description": "No usable model is loaded (see GET /system/status)."},
}
ROUTING_ERROR_RESPONSES = {**NOT_FOUND_RESPONSES, **MODEL_UNAVAILABLE_RESPONSES}
