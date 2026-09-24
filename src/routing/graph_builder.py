"""Builds the RouteWise routing graph (NetworkX DiGraph) from the Stage 2/3
DEVELOPMENT dataset — never a hardcoded/synthetic-for-this-stage graph.

Node granularity: one node per GTFS stop_id.
Edge granularity: one directed edge per (route_id, direction_id) leg
between two consecutive stops — the SCHEDULE STRUCTURE (which stops a
route connects and in what order), not one edge per individual scheduled
departure/trip instance. Stage 2's generator uses a fixed schedule
template per route+direction (identical stop sequence and inter-stop
travel times across all departures of that route+direction), so a single
REPRESENTATIVE trip_id per (route_id, direction_id) fully characterizes
the leg — confirmed against src/ingestion/generate_demo_data.py.

Disruption probability per edge is a REFERENCE-CONTEXT prediction: the
whole graph represents "expected conditions at one fixed query
datetime/weather" (routing.prediction_context in params.yaml), not a
per-departure or continuously time-varying prediction. This is a
documented simplification — see module docstring in engine.py for how a
route query can later override this per-request.

Known data artifact: travel_time is computed from the source schedule's
HH:MM:SS strings (minute granularity), and a very short leg's arrival and
departure can independently round to the same minute, producing
travel_time == 0 for that one edge. This is left as-is (not floored to a
minimum) because it's a real property of the sourced schedule data, not
something to silently paper over — see
tests/test_routing_graph.py::test_zero_travel_time_edge_is_a_real_documented_artifact.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import networkx as nx
import pandas as pd

from src.ingestion.load_raw import RAW_DIR, load_raw_tables
from src.routing.lineage import EdgeLineage
from src.routing.predict import predict_disruption_probabilities
from src.routing.prediction_source import PredictionSource
from src.utils.network_topology import compute_transfer_dependency
from src.utils.time_buckets import classify_day_period, hhmm_to_minutes, time_of_day_bucket

logger = logging.getLogger("routewise.routing.graph_builder")


@dataclass
class QueryContext:
    """The reference conditions the graph's disruption predictions are
    computed under. NOT real-time — a documented fixed/supplied point in
    time and weather (see params.yaml routing.prediction_context)."""
    query_datetime: datetime
    precipitation_mm: float
    temperature_c: float
    visibility_km: float

    @classmethod
    def from_config(cls, config: dict) -> QueryContext:
        pc = config["routing"]["prediction_context"]
        return cls(
            query_datetime=datetime.fromisoformat(pc["default_datetime"]),
            precipitation_mm=pc["default_weather"]["precipitation_mm"],
            temperature_c=pc["default_weather"]["temperature_c"],
            visibility_km=pc["default_weather"]["visibility_km"],
        )


def _select_representative_trips(trips: pd.DataFrame) -> pd.DataFrame:
    """One representative trip_id per (route_id, direction_id), preferring
    service_id=='weekday' (falls back to whatever exists otherwise). The
    stop sequence and leg times are identical across all trips of the
    same (route_id, direction_id) by construction of the generator, so
    any single representative trip fully characterizes that leg set.
    """
    trips = trips.copy()
    trips["_weekday_priority"] = (trips["service_id"] != "weekday").astype(int)
    trips = trips.sort_values(["route_id", "direction_id", "_weekday_priority", "trip_id"])
    return trips.groupby(["route_id", "direction_id"], as_index=False).first()


def _latest_route_history(interim_feature_table: pd.DataFrame) -> pd.DataFrame:
    """The most recent (max service_date) historical_delay_minutes /
    rolling_7d_delay_minutes / historical_reliability per route, from the
    REAL Stage 3 leakage-safe feature table — not fabricated. Documented
    as "latest known signal as of the end of the training data window."
    """
    sorted_df = interim_feature_table.sort_values("service_date")
    latest = sorted_df.groupby("route_id").tail(1)
    return latest.set_index("route_id")[
        ["historical_delay_minutes", "rolling_7d_delay_minutes", "historical_reliability"]
    ]


def build_routing_graph(
    prediction_source: PredictionSource,
    query_context: QueryContext,
    synthetic_config: dict,
    raw_dir: Path = RAW_DIR,
    interim_path: Path = Path("data/interim/joined_training_events.parquet"),
    preprocessor=None,
) -> tuple[nx.DiGraph, dict[str, EdgeLineage]]:
    """`synthetic_config` is configs/synthetic_data.yaml's parsed content —
    the SAME file Stage 3's feature pipeline used for day_periods/transfer
    window, so edge features stay consistent with how the model was trained.
    """
    tables = load_raw_tables(raw_dir)
    stops, routes, trips, stop_times, fares = (
        tables["stops"], tables["routes"], tables["trips"], tables["stop_times"], tables["fares"]
    )
    interim = pd.read_parquet(interim_path)
    latest_history = _latest_route_history(interim)
    qctx = query_context

    routes_by_id = routes.set_index("route_id")
    fares_by_route = fares.set_index("route_id")["fare_amount"]

    st_enriched = stop_times.merge(trips[["trip_id", "route_id", "service_id"]], on="trip_id", how="left")
    st_enriched["_arrival_minute"] = st_enriched["scheduled_arrival"].apply(hhmm_to_minutes)
    transfer_window = synthetic_config["transfer"]["window_minutes"]
    st_enriched["transfer_dependency"] = compute_transfer_dependency(st_enriched, transfer_window)
    transfer_lookup = st_enriched.set_index(["trip_id", "stop_id"])["transfer_dependency"]

    representative = _select_representative_trips(trips)

    graph = nx.DiGraph()
    for _, stop in stops.iterrows():
        graph.add_node(stop["stop_id"], stop_name=stop["stop_name"], lat=stop["stop_lat"],
                        lon=stop["stop_lon"], zone_id=stop["zone_id"])

    minute_of_day = qctx.query_datetime.hour * 60 + qctx.query_datetime.minute
    day_period_cfg = synthetic_config["day_periods"]
    day_period = classify_day_period(minute_of_day, day_period_cfg["peak_windows"], day_period_cfg["night_window"])
    tod_bucket = time_of_day_bucket(qctx.query_datetime.hour)
    day_of_week = qctx.query_datetime.weekday()
    is_weekend = int(day_of_week >= 5)

    edge_rows = []
    edge_keys = []
    lineage_map: dict[str, EdgeLineage] = {}

    for _, rep_trip in representative.iterrows():
        route_id, direction_id, trip_id = rep_trip["route_id"], rep_trip["direction_id"], rep_trip["trip_id"]
        route_info = routes_by_id.loc[route_id]
        transport_mode = route_info["transport_mode"]

        leg_stops = stop_times[stop_times["trip_id"] == trip_id].sort_values("stop_sequence")
        n_legs = len(leg_stops) - 1
        if n_legs <= 0:
            continue
        route_fare = float(fares_by_route.get(route_id, 0.0))
        leg_cost = route_fare / n_legs

        rows = leg_stops.to_dict("records")
        for a, b in zip(rows[:-1], rows[1:]):
            travel_time = hhmm_to_minutes(b["scheduled_arrival"]) - hhmm_to_minutes(a["scheduled_departure"])
            if travel_time < 0:
                travel_time += 24 * 60  # trip crosses midnight
            edge_id = f"{route_id}:{direction_id}:{a['stop_id']}->{b['stop_id']}"

            transfer_dep = transfer_lookup.get((trip_id, a["stop_id"]), 0)
            hist = latest_history.loc[route_id] if route_id in latest_history.index else None

            edge_rows.append({
                "transport_mode": transport_mode, "day_period": day_period, "time_of_day_bucket": tod_bucket,
                "hour": qctx.query_datetime.hour, "day_of_week": day_of_week, "is_weekend": is_weekend,
                "precipitation_mm": qctx.precipitation_mm, "temperature_c": qctx.temperature_c,
                "visibility_km": qctx.visibility_km, "transfer_dependency": transfer_dep,
                "historical_delay_minutes": hist["historical_delay_minutes"] if hist is not None else None,
                "rolling_7d_delay_minutes": hist["rolling_7d_delay_minutes"] if hist is not None else None,
                "historical_reliability": hist["historical_reliability"] if hist is not None else None,
            })
            edge_keys.append((a["stop_id"], b["stop_id"], route_id, direction_id, trip_id, transport_mode,
                               travel_time, leg_cost, edge_id, n_legs))

    feature_df = pd.DataFrame(edge_rows)
    disruption_probs = predict_disruption_probabilities(prediction_source, feature_df, preprocessor=preprocessor)

    for (stop_a, stop_b, route_id, direction_id, trip_id, transport_mode, travel_time, leg_cost, edge_id,
         n_legs_for_route), p in zip(edge_keys, disruption_probs):
        reliability = 1.0 - float(p)
        graph.add_edge(
            stop_a, stop_b,
            edge_id=edge_id, route_id=route_id, direction_id=int(direction_id), trip_id=trip_id,
            transport_mode=transport_mode, travel_time=float(travel_time), cost=float(leg_cost),
            disruption_probability=float(p), reliability=reliability, is_transfer=False,
        )

        lineage = EdgeLineage(edge_id=edge_id)
        lineage.add("travel_time", "data/raw/gtfs/stop_times.csv", f"trip_id={trip_id}",
                    "scheduled_arrival(b) - scheduled_departure(a), representative trip for (route_id, direction_id)",
                    is_derived=False)
        lineage.add("cost", "data/raw/gtfs/fares.csv", f"route_id={route_id}",
                    f"fare_amount / {n_legs_for_route} legs (equal apportionment across the route's legs)",
                    is_derived=True)
        lineage.add("disruption_probability", "trained model (Stage 4/5)",
                     f"model_version={prediction_source.model_version} ({prediction_source.lifecycle_stage})",
                     "predict_proba over a feature vector built from: transport_mode/route (GTFS), "
                     "transfer_dependency (derived, structural), latest known historical route stats "
                     "(data/interim/joined_training_events.parquet), and the query reference "
                     "datetime/weather (routing.prediction_context, NOT real-time)", is_derived=True)
        lineage.add("reliability", "derived", edge_id, "1 - disruption_probability", is_derived=True)
        lineage_map[edge_id] = lineage

    logger.info("Built routing graph: %d nodes, %d edges, prediction_source=%s",
                graph.number_of_nodes(), graph.number_of_edges(), prediction_source.describe())
    return graph, lineage_map
