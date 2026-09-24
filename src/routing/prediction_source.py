"""Disruption-prediction model source for the routing graph.

Stage 5 confirmed no model is currently promoted to production. This
module refuses to silently substitute a Candidate model for a Production
one — the caller must explicitly choose:

  1. "production"  — load via inference.model_loader.load_production_model();
                      raises NoProductionModelError if none exists (it
                      does not exist right now).
  2. "candidate"    — load an explicitly named registered model VERSION,
                      for controlled experiments/demonstration only.

Every PredictionSource carries its own lifecycle_stage and model_version
so callers (and the final RouteResult) can display exactly which model
produced a given prediction — never implied, never hidden.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from inference.model_loader import (
    DEFAULT_REGISTERED_MODEL_NAME,
    ModelMetadata,
    load_model_version,
    load_production_model,
)

PredictionSourceKind = Literal["production", "candidate"]


@dataclass
class PredictionSource:
    kind: PredictionSourceKind
    model: object
    metadata: ModelMetadata

    @property
    def lifecycle_stage(self) -> str | None:
        return self.metadata.lifecycle_stage

    @property
    def model_version(self) -> str:
        return self.metadata.model_version

    @property
    def is_production(self) -> bool:
        return self.kind == "production"

    def describe(self) -> dict:
        return {
            "prediction_source_kind": self.kind,
            "model_name": self.metadata.model_name,
            "model_version": self.metadata.model_version,
            "lifecycle_stage": self.metadata.lifecycle_stage,
            "is_production": self.is_production,
            "warning": None if self.is_production else (
                "This route was scored using a NON-PRODUCTION (candidate) model, "
                "for development/demonstration purposes. No model is currently "
                "promoted to production."
            ),
        }


def get_prediction_source(
    kind: PredictionSourceKind,
    model_name: str = DEFAULT_REGISTERED_MODEL_NAME,
    candidate_version: str | None = None,
    tracking_uri: str | None = None,
) -> PredictionSource:
    if kind == "production":
        model, metadata = load_production_model(model_name=model_name, tracking_uri=tracking_uri)
        return PredictionSource(kind="production", model=model, metadata=metadata)

    if kind == "candidate":
        if not candidate_version:
            raise ValueError(
                "kind='candidate' requires an explicit candidate_version — "
                "the routing engine never silently picks a candidate model."
            )
        model, metadata = load_model_version(candidate_version, model_name=model_name, tracking_uri=tracking_uri)
        return PredictionSource(kind="candidate", model=model, metadata=metadata)

    raise ValueError(f"Unknown prediction source kind '{kind}', expected 'production' or 'candidate'")
