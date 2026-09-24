"""Tests for path aggregation: cost/time/risk aggregation, transfer
counting (no double-counting), and edge cases."""
import networkx as nx
import pytest

from src.routing.path_aggregation import InvalidPathError, aggregate_path, count_transfers, path_to_edges

TRANSFER_CONFIG = {"time_minutes": 5.0, "cost": 2.0, "reliability_penalty": 0.02}


def _graph_with_transfer() -> nx.DiGraph:
    g = nx.DiGraph()
    for n in ["A", "B", "C"]:
        g.add_node(n, lat=0.0, lon=0.0)
    g.add_edge("A", "B", edge_id="e1", route_id="R1", trip_id="T1", transport_mode="bus",
               travel_time=10.0, cost=2.0, disruption_probability=0.1, reliability=0.9, is_transfer=False)
    # different route -> transfer
    g.add_edge("B", "C", edge_id="e2", route_id="R2", trip_id="T2", transport_mode="rail",
               travel_time=15.0, cost=5.0, disruption_probability=0.2, reliability=0.8, is_transfer=False)
    return g


def _graph_no_transfer() -> nx.DiGraph:
    g = nx.DiGraph()
    for n in ["A", "B", "C"]:
        g.add_node(n, lat=0.0, lon=0.0)
    g.add_edge("A", "B", edge_id="e1", route_id="R1", trip_id="T1", transport_mode="bus",
               travel_time=10.0, cost=2.0, disruption_probability=0.1, reliability=0.9, is_transfer=False)
    g.add_edge("B", "C", edge_id="e2", route_id="R1", trip_id="T1", transport_mode="bus",  # same route -> no transfer
               travel_time=15.0, cost=5.0, disruption_probability=0.2, reliability=0.8, is_transfer=False)
    return g


def test_path_to_edges_returns_edge_data_in_order():
    g = _graph_with_transfer()
    edges = path_to_edges(g, ["A", "B", "C"])
    assert [e["edge_id"] for e in edges] == ["e1", "e2"]


def test_path_to_edges_missing_edge_raises():
    g = _graph_with_transfer()
    with pytest.raises(InvalidPathError):
        path_to_edges(g, ["A", "C"])  # no direct A->C edge


def test_count_transfers_detects_route_change():
    g = _graph_with_transfer()
    edges = path_to_edges(g, ["A", "B", "C"])
    assert count_transfers(edges) == 1


def test_count_transfers_no_transfer_same_route():
    g = _graph_no_transfer()
    edges = path_to_edges(g, ["A", "B", "C"])
    assert count_transfers(edges) == 0


def test_count_transfers_single_edge_has_zero_transfers():
    g = _graph_with_transfer()
    edges = path_to_edges(g, ["A", "B"])
    assert count_transfers(edges) == 0


def test_aggregate_path_origin_equals_destination():
    g = _graph_with_transfer()
    result = aggregate_path(g, ["A"], TRANSFER_CONFIG)
    assert result["total_time"] == 0.0
    assert result["total_cost"] == 0.0
    assert result["reliability"] == 1.0
    assert result["disruption_risk"] == 0.0
    assert result["transfer_count"] == 0
    assert result["segments"] == []


def test_aggregate_path_sums_time_and_cost_plus_transfer_penalty():
    g = _graph_with_transfer()
    result = aggregate_path(g, ["A", "B", "C"], TRANSFER_CONFIG)
    assert result["total_time"] == pytest.approx(10.0 + 15.0 + 5.0)  # +1 transfer penalty
    assert result["total_cost"] == pytest.approx(2.0 + 5.0 + 2.0)
    assert result["transfer_count"] == 1


def test_aggregate_path_no_transfer_penalty_when_same_route():
    g = _graph_no_transfer()
    result = aggregate_path(g, ["A", "B", "C"], TRANSFER_CONFIG)
    assert result["total_time"] == pytest.approx(25.0)  # no penalty added
    assert result["transfer_count"] == 0


def test_aggregate_path_reliability_is_product_minus_transfer_penalty():
    g = _graph_with_transfer()
    result = aggregate_path(g, ["A", "B", "C"], TRANSFER_CONFIG)
    expected = 0.9 * 0.8 - 0.02
    assert result["reliability"] == pytest.approx(expected)
    assert result["disruption_risk"] == pytest.approx(1 - expected)


def test_aggregate_path_transport_modes_are_deduped_and_ordered():
    g = _graph_with_transfer()
    result = aggregate_path(g, ["A", "B", "C"], TRANSFER_CONFIG)
    assert result["transport_modes"] == ["bus", "rail"]


def test_aggregate_path_zero_cost_route():
    g = nx.DiGraph()
    g.add_node("A", lat=0.0, lon=0.0)
    g.add_node("B", lat=0.0, lon=0.0)
    g.add_edge("A", "B", edge_id="e1", route_id="R1", trip_id="T1", transport_mode="bus",
               travel_time=5.0, cost=0.0, disruption_probability=0.0, reliability=1.0, is_transfer=False)
    result = aggregate_path(g, ["A", "B"], TRANSFER_CONFIG)
    assert result["total_cost"] == pytest.approx(0.0)
    assert result["reliability"] == pytest.approx(1.0)


def test_aggregate_path_high_risk_route_caps_reliability_at_zero():
    g = nx.DiGraph()
    for n in ["A", "B", "C"]:
        g.add_node(n, lat=0.0, lon=0.0)
    g.add_edge("A", "B", edge_id="e1", route_id="R1", trip_id="T1", transport_mode="bus",
               travel_time=5.0, cost=1.0, disruption_probability=0.99, reliability=0.01, is_transfer=False)
    g.add_edge("B", "C", edge_id="e2", route_id="R2", trip_id="T2", transport_mode="bus",
               travel_time=5.0, cost=1.0, disruption_probability=0.99, reliability=0.01, is_transfer=False)
    result = aggregate_path(g, ["A", "B", "C"], TRANSFER_CONFIG)
    assert 0.0 <= result["reliability"] <= 1.0  # never goes negative despite penalty subtraction
    assert result["disruption_risk"] <= 1.0


def test_aggregate_path_empty_path_raises():
    g = _graph_with_transfer()
    with pytest.raises(InvalidPathError):
        aggregate_path(g, [], TRANSFER_CONFIG)
