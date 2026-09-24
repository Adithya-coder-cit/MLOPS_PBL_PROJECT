"""Tests for multi-strategy candidate route generation."""
import networkx as nx

from src.routing.candidates import generate_candidate_paths, k_shortest_paths_by_time


def _diamond_graph() -> nx.DiGraph:
    """A -> {B, C} -> D: two genuinely different paths, plus a slower
    third alternative through E, for k-shortest-paths to find."""
    g = nx.DiGraph()
    for n in ["A", "B", "C", "D", "E"]:
        g.add_node(n, lat=0.0, lon=0.0)
    g.add_edge("A", "B", edge_id="e1", route_id="R1", trip_id="T1", transport_mode="bus",
               travel_time=10.0, cost=5.0, disruption_probability=0.1, reliability=0.9, is_transfer=False)
    g.add_edge("B", "D", edge_id="e2", route_id="R1", trip_id="T1", transport_mode="bus",
               travel_time=10.0, cost=5.0, disruption_probability=0.1, reliability=0.9, is_transfer=False)
    g.add_edge("A", "C", edge_id="e3", route_id="R2", trip_id="T2", transport_mode="rail",
               travel_time=8.0, cost=15.0, disruption_probability=0.3, reliability=0.7, is_transfer=False)
    g.add_edge("C", "D", edge_id="e4", route_id="R2", trip_id="T2", transport_mode="rail",
               travel_time=8.0, cost=15.0, disruption_probability=0.3, reliability=0.7, is_transfer=False)
    g.add_edge("A", "E", edge_id="e5", route_id="R3", trip_id="T3", transport_mode="bus",
               travel_time=30.0, cost=2.0, disruption_probability=0.05, reliability=0.95, is_transfer=False)
    g.add_edge("E", "D", edge_id="e6", route_id="R3", trip_id="T3", transport_mode="bus",
               travel_time=30.0, cost=2.0, disruption_probability=0.05, reliability=0.95, is_transfer=False)
    return g


CONFIG = {"routing": {"candidate_generation": {
    "k_shortest_paths": 3, "strategies": ["shortest_time", "lowest_cost", "lowest_risk", "k_shortest_time"],
}}}


def test_generate_candidate_paths_finds_multiple_distinct_routes():
    g = _diamond_graph()
    paths = generate_candidate_paths(g, "A", "D", CONFIG)
    assert len(paths) >= 2
    assert len(set(tuple(p) for p in paths)) == len(paths)  # de-duplicated


def test_generate_candidate_paths_includes_the_time_optimal_path():
    g = _diamond_graph()
    paths = generate_candidate_paths(g, "A", "D", CONFIG)
    assert ["A", "C", "D"] in paths  # fastest (8+8=16 min)


def test_generate_candidate_paths_includes_the_cost_optimal_path():
    g = _diamond_graph()
    paths = generate_candidate_paths(g, "A", "D", CONFIG)
    assert ["A", "E", "D"] in paths  # cheapest (2+2=4 units)


def test_generate_candidate_paths_origin_equals_destination():
    g = _diamond_graph()
    paths = generate_candidate_paths(g, "A", "A", CONFIG)
    assert paths == [["A"]]


def test_generate_candidate_paths_unreachable_returns_empty():
    g = _diamond_graph()
    g.add_node("ISOLATED", lat=9.0, lon=9.0)
    paths = generate_candidate_paths(g, "A", "ISOLATED", CONFIG)
    assert paths == []


def test_k_shortest_paths_respects_k_limit():
    g = _diamond_graph()
    paths = k_shortest_paths_by_time(g, "A", "D", k=2)
    assert len(paths) <= 2


def test_k_shortest_paths_single_strategy_subset():
    g = _diamond_graph()
    single_strategy_config = {"routing": {"candidate_generation": {
        "k_shortest_paths": 3, "strategies": ["shortest_time"],
    }}}
    paths = generate_candidate_paths(g, "A", "D", single_strategy_config)
    assert len(paths) == 1
    assert paths[0] == ["A", "C", "D"]
