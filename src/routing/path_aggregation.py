"""Aggregates a raw path (list of stop_id nodes) into route-level
totals: time, cost, reliability, disruption risk, transfer count, and
per-segment detail. Transfer penalties are applied ONCE per transfer
point here (not baked into per-edge search weights, not applied twice).
"""
from __future__ import annotations

import networkx as nx

from src.decision_engine.reliability import route_reliability


class InvalidPathError(Exception):
    pass


def path_to_edges(graph: nx.DiGraph, path: list[str]) -> list[dict]:
    if len(path) < 2:
        return []
    edges = []
    for a, b in zip(path[:-1], path[1:]):
        if not graph.has_edge(a, b):
            raise InvalidPathError(f"No edge {a} -> {b} in graph")
        edges.append(graph.edges[a, b])
    return edges


def count_transfers(edges: list[dict]) -> int:
    """A transfer occurs whenever consecutive ride-legs belong to a
    different route_id — detected here at aggregation time, not as a
    separate graph edge (see graph_builder.py module docstring)."""
    if len(edges) < 2:
        return 0
    return sum(1 for e1, e2 in zip(edges[:-1], edges[1:]) if e1["route_id"] != e2["route_id"])


def aggregate_path(graph: nx.DiGraph, path: list[str], transfer_config: dict) -> dict:
    if len(path) == 0:
        raise InvalidPathError("Path must have at least one node")
    if len(path) == 1:
        # origin == destination: a trivial, zero-length, fully reliable route.
        return {
            "path": path, "segments": [], "total_time": 0.0, "total_cost": 0.0,
            "reliability": 1.0, "disruption_risk": 0.0, "transfer_count": 0,
            "transport_modes": [],
        }

    edges = path_to_edges(graph, path)
    n_transfers = count_transfers(edges)

    total_time = sum(e["travel_time"] for e in edges) + n_transfers * transfer_config["time_minutes"]
    total_cost = sum(e["cost"] for e in edges) + n_transfers * transfer_config["cost"]

    edge_probs = [e["disruption_probability"] for e in edges]
    reliability = route_reliability(edge_probs) - n_transfers * transfer_config["reliability_penalty"]
    reliability = max(0.0, min(1.0, reliability))
    disruption_risk = 1.0 - reliability

    transport_modes = list(dict.fromkeys(e["transport_mode"] for e in edges))  # ordered, deduped

    segments = [
        {
            "edge_id": e["edge_id"], "from_stop": path[i], "to_stop": path[i + 1], "route_id": e["route_id"],
            "trip_id": e["trip_id"], "transport_mode": e["transport_mode"],
            "travel_time": e["travel_time"], "cost": e["cost"],
            "disruption_probability": e["disruption_probability"], "reliability": e["reliability"],
            "is_transfer_point": i > 0 and edges[i - 1]["route_id"] != e["route_id"],
        }
        for i, e in enumerate(edges)
    ]

    return {
        "path": path, "segments": segments, "total_time": total_time, "total_cost": total_cost,
        "reliability": reliability, "disruption_risk": disruption_risk, "transfer_count": n_transfers,
        "transport_modes": transport_modes,
    }
