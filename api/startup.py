"""Builds AppState once at application startup. Model-loading failures
are caught here and stored on the state (not raised) — the app must
still start and serve /health even if the configured model is
unavailable; inference endpoints then fail explicitly per-request
(see api/exceptions.py) rather than the whole app crashing.
"""
from __future__ import annotations

import logging
from pathlib import Path

import joblib
import pandas as pd
import yaml

from api.config import Settings
from api.services.inference_service import InferenceService
from api.services.routing_service import RoutingService
from api.state import AppState
from src.ingestion.load_raw import load_raw_tables
from src.monitoring.operational import OperationalMetrics
from src.routing.graph_builder import QueryContext, build_routing_graph, list_routes_with_stops
from src.routing.prediction_source import get_prediction_source

logger = logging.getLogger("routewise.api")

PARAMS_PATH = Path("params.yaml")
SYNTHETIC_CONFIG_PATH = Path("configs/synthetic_data.yaml")
PREPROCESSOR_PATH = Path("data/processed/preprocessor.joblib")
INTERIM_PATH = Path("data/interim/joined_training_events.parquet")


def build_app_state(settings: Settings) -> AppState:
    params_config = yaml.safe_load(PARAMS_PATH.read_text(encoding="utf-8"))
    synthetic_config = yaml.safe_load(SYNTHETIC_CONFIG_PATH.read_text(encoding="utf-8"))

    # Stops (and real route structure) are static GTFS data — loaded
    # regardless of model availability, so the frontend's origin/destination
    # pickers and Network Map work even if the model fails to load (only
    # route scoring/prediction actually needs the model).
    raw_tables = load_raw_tables()
    stops = raw_tables["stops"][["stop_id", "stop_name", "stop_lat", "stop_lon", "zone_id"]].rename(
        columns={"stop_lat": "lat", "stop_lon": "lon"}
    ).to_dict("records")
    routes_with_stops = list_routes_with_stops()

    try:
        source = get_prediction_source(
            kind=settings.model_source, model_name=settings.registered_model_name,
            candidate_version=settings.model_candidate_version, tracking_uri=settings.mlflow_tracking_uri,
        )
    except Exception as e:
        logger.warning("Model unavailable at startup (source=%s): %s", settings.model_source, e)
        return AppState(
            settings=settings, params_config=params_config, prediction_source=None, model_metadata=None,
            graph=None, inference_service=None, routing_service=None, model_load_error=str(e), stops=stops,
            routes_with_stops=routes_with_stops, operational_metrics=OperationalMetrics(),
        )

    preprocessor = joblib.load(PREPROCESSOR_PATH) if PREPROCESSOR_PATH.exists() else None
    interim = pd.read_parquet(INTERIM_PATH)

    qctx = QueryContext.from_config(params_config)
    graph, _lineage = build_routing_graph(source, qctx, synthetic_config, preprocessor=preprocessor)

    # Real-data fix, not a message change: a handful of GTFS stops genuinely
    # have zero scheduled trips in this dataset (verified via the routing
    # graph's own node degree, not guessed) -- flagging them here lets the
    # frontend keep users from picking a stop that can never be reached,
    # instead of letting them search and then explaining why it failed.
    for stop in stops:
        stop["has_scheduled_service"] = graph.degree(stop["stop_id"]) > 0

    inference_service = InferenceService(
        source, preprocessor, raw_tables, interim, synthetic_config,
        decision_threshold=params_config["training"]["decision_threshold"],
    )
    routing_service = RoutingService(
        graph, source, params_config, data_version=source.metadata.dataset_version,
    )

    logger.info("App state initialized: model=%s v%s (%s), graph=%d nodes/%d edges",
                source.metadata.model_name, source.metadata.model_version, source.lifecycle_stage,
                graph.number_of_nodes(), graph.number_of_edges())

    return AppState(
        settings=settings, params_config=params_config, prediction_source=source,
        model_metadata=source.metadata, graph=graph, inference_service=inference_service,
        routing_service=routing_service, model_load_error=None, stops=stops,
        routes_with_stops=routes_with_stops, operational_metrics=OperationalMetrics(),
    )
