"""Dijkstra/A* tests against a small, hand-built graph (precise control
over edge cases) plus a couple of integration checks against the real
routing graph.
"""
import networkx as nx
import pytest

from src.routing.path_search import NoPathFoundError, astar_shortest_path, dijkstra_shortest_path
from tests.conftest import requires_routing_stack


def _tiny_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("A", lat=0.0, lon=0.0)
    g.add_node("B", lat=0.0, lon=0.1)
    g.add_node("C", lat=0.0, lon=0.2)
    g.add_node("D", lat=0.0, lon=0.3)
    g.add_node("ISOLATED", lat=5.0, lon=5.0)

    # A -> B -> D : slow but cheap and reliable
    g.add_edge("A", "B", edge_id="e1", route_id="R1", trip_id="T1", transport_mode="bus",
               travel_time=20.0, cost=1.0, disruption_probability=0.05, reliability=0.95, is_transfer=False)
    g.add_edge("B", "D", edge_id="e2", route_id="R1", trip_id="T1", transport_mode="bus",
               travel_time=20.0, cost=1.0, disruption_probability=0.05, reliability=0.95, is_transfer=False)
    # A -> C -> D : fast but expensive and risky
    g.add_edge("A", "C", edge_id="e3", route_id="R2", trip_id="T2", transport_mode="rail",
               travel_time=5.0, cost=10.0, disruption_probability=0.5, reliability=0.5, is_transfer=False)
    g.add_edge("C", "D", edge_id="e4", route_id="R2", trip_id="T2", transport_mode="rail",
               travel_time=5.0, cost=10.0, disruption_probability=0.5, reliability=0.5, is_transfer=False)
    return g


def test_dijkstra_time_objective_prefers_fast_expensive_path():
    g = _tiny_graph()
    path = dijkstra_shortest_path(g, "A", "D", "time")
    assert path == ["A", "C", "D"]


def test_dijkstra_cost_objective_prefers_slow_cheap_path():
    g = _tiny_graph()
    path = dijkstra_shortest_path(g, "A", "D", "cost")
    assert path == ["A", "B", "D"]


def test_dijkstra_risk_objective_prefers_reliable_path():
    g = _tiny_graph()
    path = dijkstra_shortest_path(g, "A", "D", "risk")
    assert path == ["A", "B", "D"]


def test_dijkstra_combined_objective_returns_valid_path():
    g = _tiny_graph()
    path = dijkstra_shortest_path(g, "A", "D", "combined", decision_weights={"alpha": 1, "beta": 1, "gamma": 1})
    assert path[0] == "A" and path[-1] == "D"
    for a, b in zip(path[:-1], path[1:]):
        assert g.has_edge(a, b)


def test_dijkstra_origin_equals_destination_returns_single_node():
    g = _tiny_graph()
    assert dijkstra_shortest_path(g, "A", "A", "time") == ["A"]


def test_dijkstra_unreachable_destination_raises():
    g = _tiny_graph()
    with pytest.raises(NoPathFoundError):
        dijkstra_shortest_path(g, "A", "ISOLATED", "time")


def test_dijkstra_missing_node_raises():
    g = _tiny_graph()
    with pytest.raises(NoPathFoundError):
        dijkstra_shortest_path(g, "A", "NOT_A_REAL_STOP", "time")


def test_astar_time_objective_produces_valid_path_matching_dijkstra():
    g = _tiny_graph()
    astar_path = astar_shortest_path(g, "A", "D", "time")
    dijkstra_path = dijkstra_shortest_path(g, "A", "D", "time")
    assert astar_path == dijkstra_path


def test_astar_risk_objective_with_zero_heuristic_produces_valid_path():
    g = _tiny_graph()
    path = astar_shortest_path(g, "A", "D", "risk")
    assert path == ["A", "B", "D"]  # same as Dijkstra, since heuristic=0 for risk


def test_astar_origin_equals_destination():
    g = _tiny_graph()
    assert astar_shortest_path(g, "A", "A", "time") == ["A"]


def test_astar_unreachable_destination_raises():
    g = _tiny_graph()
    with pytest.raises(NoPathFoundError):
        astar_shortest_path(g, "A", "ISOLATED", "time")


def test_astar_produces_valid_edges_for_every_step():
    g = _tiny_graph()
    path = astar_shortest_path(g, "A", "D", "time")
    for a, b in zip(path[:-1], path[1:]):
        assert g.has_edge(a, b)


# --- integration against the real graph ---

@requires_routing_stack
def test_dijkstra_on_real_graph_finds_valid_path(routing_graph):
    graph, _ = routing_graph
    giant = max(nx.weakly_connected_components(graph), key=len)
    nodes = list(giant)
    origin, destination = nodes[0], nodes[-1]
    if not nx.has_path(graph, origin, destination):
        pytest.skip("chosen node pair happens to be disconnected in this component ordering")
    path = dijkstra_shortest_path(graph, origin, destination, "time")
    assert path[0] == origin and path[-1] == destination


@requires_routing_stack
def test_real_graph_has_disconnected_components(routing_graph):
    """Proves the graph genuinely has isolated/disconnected stops (not
    every synthetic stop is served by a route) — an honest property of
    the generated dataset, exercised here rather than assumed."""
    graph, _ = routing_graph
    components = list(nx.weakly_connected_components(graph))
    assert len(components) > 1
