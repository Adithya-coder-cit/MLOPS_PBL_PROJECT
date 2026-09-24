"""Generates MULTIPLE candidate routes for a query, from several distinct
strategies (not a single shortest-path call): shortest-time, lowest-cost,
lowest-risk (each via Dijkstra), plus k-shortest-time paths for genuine
alternatives. Duplicate paths across strategies are de-duplicated before
scoring. See params.yaml routing.candidate_generation.
"""
from __future__ import annotations

from itertools import islice

import networkx as nx

from src.routing.path_search import NoPathFoundError, dijkstra_shortest_path


def k_shortest_paths_by_time(graph: nx.DiGraph, origin: str, destination: str, k: int) -> list[list[str]]:
    if origin == destination:
        return [[origin]]
    try:
        generator = nx.shortest_simple_paths(graph, origin, destination, weight="travel_time")
        return list(islice(generator, k))
    except nx.NetworkXNoPath:
        return []
    except nx.NodeNotFound:
        return []


def generate_candidate_paths(graph: nx.DiGraph, origin: str, destination: str, config: dict) -> list[list[str]]:
    """Returns a de-duplicated list of raw paths (node-id lists). Does
    NOT score them — see engine.py for scoring/ranking. Empty list means
    no path exists under any strategy (unreachable destination).
    """
    cg = config["routing"]["candidate_generation"]
    strategies = cg["strategies"]
    k = cg["k_shortest_paths"]

    seen: set[tuple] = set()
    candidates: list[list[str]] = []

    def _add(path: list[str]) -> None:
        key = tuple(path)
        if key not in seen:
            seen.add(key)
            candidates.append(path)

    if "shortest_time" in strategies:
        try:
            _add(dijkstra_shortest_path(graph, origin, destination, "time"))
        except NoPathFoundError:
            pass
    if "lowest_cost" in strategies:
        try:
            _add(dijkstra_shortest_path(graph, origin, destination, "cost"))
        except NoPathFoundError:
            pass
    if "lowest_risk" in strategies:
        try:
            _add(dijkstra_shortest_path(graph, origin, destination, "risk"))
        except NoPathFoundError:
            pass
    if "k_shortest_time" in strategies:
        for path in k_shortest_paths_by_time(graph, origin, destination, k):
            _add(path)

    return candidates
