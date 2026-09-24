"""Adaptive rerouting: NOT real-time (no live data feed is connected —
Stage 6 explicitly scopes this out). This is an "adaptive rerouting
CAPABILITY": given a caller-supplied update to disruption probabilities
(e.g. from a hypothetical new prediction run), recompute whether the
current route is still the best recommendation.
"""
from __future__ import annotations

import networkx as nx

from src.routing.engine import recommend_routes
from src.routing.prediction_source import PredictionSource
from src.routing.route_result import RouteResult


def apply_disruption_updates(graph: nx.DiGraph, updated_edge_probabilities: dict[str, float]) -> nx.DiGraph:
    """Returns a NEW graph (the input is never mutated) with the given
    edges' disruption_probability/reliability updated. Keys are edge_id
    strings (graph.edges[u, v]["edge_id"]), values are new probabilities.
    """
    updated = graph.copy()
    edge_id_to_uv = {d["edge_id"]: (u, v) for u, v, d in updated.edges(data=True)}
    for edge_id, new_p in updated_edge_probabilities.items():
        if edge_id not in edge_id_to_uv:
            raise KeyError(f"Unknown edge_id '{edge_id}' — not present in this graph")
        if not 0.0 <= new_p <= 1.0:
            raise ValueError(f"disruption_probability must be in [0,1], got {new_p} for edge {edge_id}")
        u, v = edge_id_to_uv[edge_id]
        updated.edges[u, v]["disruption_probability"] = float(new_p)
        updated.edges[u, v]["reliability"] = 1.0 - float(new_p)
    return updated


def reroute(
    current_route: RouteResult, updated_edge_probabilities: dict[str, float], graph: nx.DiGraph,
    prediction_source: PredictionSource, config: dict, data_version: str | None = None,
) -> dict:
    """1. update affected edge risk/reliability
       2-4. recalculate scores, regenerate candidates, compare
       5. return the recommended route per the configured decision policy

    Returns {"updated_graph", "recommended_route", "changed", "previous_route_id",
    "all_candidates"} — "changed" is True iff the top recommendation's
    route_id differs from current_route.route_id.
    """
    updated_graph = apply_disruption_updates(graph, updated_edge_probabilities)

    candidates = recommend_routes(
        updated_graph, current_route.origin, current_route.destination, prediction_source, config,
        data_version=data_version, top_n=config["routing"]["candidate_generation"]["k_shortest_paths"],
    )
    recommended = candidates[0]

    return {
        "updated_graph": updated_graph,
        "recommended_route": recommended,
        "changed": recommended.route_id != current_route.route_id,
        "previous_route_id": current_route.route_id,
        "all_candidates": candidates,
    }
