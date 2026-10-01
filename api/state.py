"""Application state, built once at startup and reused for every
request — the model and routing graph are NOT reloaded/rebuilt per
request (Stage 7 §11)."""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from api.config import Settings
from api.services.inference_service import InferenceService
from api.services.routing_service import RoutingService
from inference.model_loader import ModelMetadata
from src.monitoring.operational import OperationalMetrics
from src.routing.prediction_source import PredictionSource


@dataclass
class AppState:
    settings: Settings
    params_config: dict
    prediction_source: PredictionSource | None
    model_metadata: ModelMetadata | None
    graph: nx.DiGraph | None
    inference_service: InferenceService | None
    routing_service: RoutingService | None
    model_load_error: str | None
    stops: list[dict]  # loaded independently of model availability — static GTFS data
    routes_with_stops: list[dict]  # real route -> ordered real stop_ids, for the Network Map's route picker
    operational_metrics: OperationalMetrics  # live request counters, see api/middleware.py

    @property
    def model_available(self) -> bool:
        return self.prediction_source is not None
