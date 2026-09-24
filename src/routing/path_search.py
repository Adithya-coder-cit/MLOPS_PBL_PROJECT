"""Dijkstra and A* over the routing graph, with a configurable scalar
edge weight selected by `objective`.

Objectives:
- "time": minimizes total travel_time. Admissible A* heuristic:
  great-circle (haversine) distance to the target divided by the fastest
  mode's speed in the graph — a genuine lower bound on remaining travel
  time (can't arrive faster than max possible speed permits).
- "cost": minimizes total monetary cost.
- "risk": minimizes total disruption risk, via the standard
  -log(reliability) transform (see decision_engine/reliability.py) so
  that summing edge weights along a path corresponds to minimizing the
  path's overall disruption risk under the independence assumption.
- "combined": minimizes alpha*cost + beta*time - gamma*log(reliability)
  using the RAW (unnormalized) per-edge units and the baseline decision
  weights — a search-time heuristic for generating a candidate, distinct
  from the final per-candidate scoring done after normalization (see
  decision_engine/scoring.py and engine.py).

No admissible, non-trivial A* heuristic exists for "cost", "risk", or
"combined" without fabricating one (cost/risk have no geometric lower
bound analogous to distance/speed) — for those objectives A* runs with
heuristic=0, which is always admissible but provides no speedup over
Dijkstra. This is a documented limitation, not a bug.
"""
from __future__ import annotations

import math

import networkx as nx

from src.decision_engine.reliability import reliability_to_dijkstra_weight

Objective = str  # "time" | "cost" | "risk" | "combined"


class NoPathFoundError(Exception):
    pass


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def edge_weight_fn(objective: Objective, decision_weights: dict | None = None):
    if objective == "time":
        return lambda u, v, d: d["travel_time"]
    if objective == "cost":
        return lambda u, v, d: d["cost"]
    if objective == "risk":
        return lambda u, v, d: reliability_to_dijkstra_weight(d["reliability"])
    if objective == "combined":
        w = decision_weights or {"alpha": 1 / 3, "beta": 1 / 3, "gamma": 1 / 3}
        return lambda u, v, d: (
            w["alpha"] * d["cost"] + w["beta"] * d["travel_time"]
            - w["gamma"] * math.log(max(d["reliability"], 1e-6))
        )
    raise ValueError(f"Unknown objective '{objective}', expected time/cost/risk/combined")


def dijkstra_shortest_path(graph: nx.DiGraph, origin: str, destination: str, objective: Objective,
                            decision_weights: dict | None = None) -> list[str]:
    if origin == destination:
        return [origin]
    weight = edge_weight_fn(objective, decision_weights)
    try:
        return nx.dijkstra_path(graph, origin, destination, weight=weight)
    except nx.NetworkXNoPath as e:
        raise NoPathFoundError(f"No path from {origin} to {destination} (objective={objective})") from e
    except nx.NodeNotFound as e:
        raise NoPathFoundError(str(e)) from e


def _max_speed_km_per_min(graph: nx.DiGraph) -> float:
    speeds = []
    for a, b, d in graph.edges(data=True):
        if d["travel_time"] > 0:
            dist = _haversine_km(graph.nodes[a]["lat"], graph.nodes[a]["lon"],
                                  graph.nodes[b]["lat"], graph.nodes[b]["lon"])
            speeds.append(dist / d["travel_time"])
    return max(speeds) if speeds else 1.0


def astar_shortest_path(graph: nx.DiGraph, origin: str, destination: str, objective: Objective,
                         decision_weights: dict | None = None) -> list[str]:
    if origin == destination:
        return [origin]
    weight = edge_weight_fn(objective, decision_weights)

    if objective == "time":
        max_speed = _max_speed_km_per_min(graph)

        def heuristic(u, v):
            dist = _haversine_km(graph.nodes[u]["lat"], graph.nodes[u]["lon"],
                                  graph.nodes[v]["lat"], graph.nodes[v]["lon"])
            return dist / max_speed  # admissible: can't be faster than max observed speed
    else:
        def heuristic(u, v):
            return 0.0  # admissible (never overestimates) but not informative — see module docstring

    try:
        return nx.astar_path(graph, origin, destination, heuristic=heuristic, weight=weight)
    except nx.NetworkXNoPath as e:
        raise NoPathFoundError(f"No path from {origin} to {destination} (objective={objective})") from e
    except nx.NodeNotFound as e:
        raise NoPathFoundError(str(e)) from e
