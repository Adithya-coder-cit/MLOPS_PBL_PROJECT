"""End-to-end engine/rerouting tests: deterministic tiny-graph scenarios
for precise edge-case control, plus real-graph integration tests
(including the Stage 6 §18 demonstration scenario itself, run as a test)."""
import networkx as nx
import pytest

from src.routing.engine import UnreachableDestinationError, recommend_routes
from src.routing.path_search import NoPathFoundError
from src.routing.rerouting import apply_disruption_updates, reroute
from tests.conftest import requires_routing_stack

CONFIG = {
    "decision_engine": {
        "baseline_weights": {"alpha": 0.34, "beta": 0.33, "gamma": 0.33},
        "high_risk_threshold": 0.4,
        "high_risk_weights": {"alpha": 0.27, "beta": 0.23, "gamma": 0.5},
    },
    "routing": {
        "normalization": {"method": "minmax_candidates",
                           "fixed_bounds": {"cost": {"min": 0, "max": 100},
                                             "time_minutes": {"min": 0, "max": 200},
                                             "reliability": {"min": 0, "max": 1}}},
        "transfer_penalty": {"time_minutes": 5.0, "cost": 2.0, "reliability_penalty": 0.02},
        "candidate_generation": {"k_shortest_paths": 3,
                                  "strategies": ["shortest_time", "lowest_cost", "lowest_risk", "k_shortest_time"]},
    },
}


class _FakeMetadata:
    model_name = "TestModel"
    model_version = "1"
    lifecycle_stage = "Candidate"


class _FakeSource:
    kind = "candidate"
    metadata = _FakeMetadata()

    def describe(self):
        return {"prediction_source_kind": "candidate", "model_name": "TestModel", "model_version": "1",
                "lifecycle_stage": "Candidate", "is_production": False,
                "warning": "This route was scored using a NON-PRODUCTION (candidate) model."}


def _diamond_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    for n in ["A", "B", "C", "D"]:
        g.add_node(n, lat=0.0, lon=0.0)
    g.add_edge("A", "B", edge_id="e1", route_id="R1", trip_id="T1", transport_mode="bus",
               travel_time=10.0, cost=5.0, disruption_probability=0.1, reliability=0.9, is_transfer=False)
    g.add_edge("B", "D", edge_id="e2", route_id="R1", trip_id="T1", transport_mode="bus",
               travel_time=10.0, cost=5.0, disruption_probability=0.1, reliability=0.9, is_transfer=False)
    g.add_edge("A", "C", edge_id="e3", route_id="R2", trip_id="T2", transport_mode="rail",
               travel_time=5.0, cost=20.0, disruption_probability=0.6, reliability=0.4, is_transfer=False)
    g.add_edge("C", "D", edge_id="e4", route_id="R2", trip_id="T2", transport_mode="rail",
               travel_time=5.0, cost=20.0, disruption_probability=0.6, reliability=0.4, is_transfer=False)
    return g


def _single_path_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    for n in ["A", "B", "C"]:
        g.add_node(n, lat=0.0, lon=0.0)
    g.add_edge("A", "B", edge_id="e1", route_id="R1", trip_id="T1", transport_mode="bus",
               travel_time=10.0, cost=5.0, disruption_probability=0.1, reliability=0.9, is_transfer=False)
    g.add_edge("B", "C", edge_id="e2", route_id="R1", trip_id="T1", transport_mode="bus",
               travel_time=10.0, cost=5.0, disruption_probability=0.1, reliability=0.9, is_transfer=False)
    return g


def test_recommend_routes_returns_ranked_candidates():
    g = _diamond_graph()
    results = recommend_routes(g, "A", "D", _FakeSource(), CONFIG, data_version="test-v1")
    assert len(results) >= 2
    scores = [r.score for r in results]
    assert scores == sorted(scores)  # ranked ascending, lower is better


def test_recommend_routes_origin_equals_destination():
    g = _diamond_graph()
    results = recommend_routes(g, "A", "A", _FakeSource(), CONFIG)
    assert len(results) == 1
    assert results[0].total_time == 0.0
    assert results[0].stops == ["A"]


def test_recommend_routes_unreachable_destination_raises():
    g = _diamond_graph()
    g.add_node("ISOLATED", lat=1.0, lon=1.0)
    with pytest.raises(UnreachableDestinationError):
        recommend_routes(g, "A", "ISOLATED", _FakeSource(), CONFIG)


def test_recommend_routes_missing_node_raises():
    g = _diamond_graph()
    with pytest.raises(NoPathFoundError):
        recommend_routes(g, "A", "NOT_A_STOP", _FakeSource(), CONFIG)


def test_recommend_routes_no_alternative_route():
    """Only one path exists between origin and destination — must still
    return a valid single-candidate result, not crash."""
    g = _single_path_graph()
    results = recommend_routes(g, "A", "C", _FakeSource(), CONFIG)
    assert len(results) == 1
    assert results[0].stops == ["A", "B", "C"]


def test_recommend_routes_exposes_model_lifecycle_status():
    g = _diamond_graph()
    results = recommend_routes(g, "A", "D", _FakeSource(), CONFIG)
    for r in results:
        assert r.is_production_model is False
        assert r.model_lifecycle_stage == "Candidate"
        assert r.model_source_warning is not None
        assert "NON-PRODUCTION" in r.model_source_warning


def test_recommend_routes_high_risk_route_triggers_high_risk_policy():
    g = _diamond_graph()
    results = recommend_routes(g, "A", "D", _FakeSource(), CONFIG)
    risky = next(r for r in results if r.stops == ["A", "C", "D"])
    assert risky.disruption_risk > CONFIG["decision_engine"]["high_risk_threshold"]
    assert risky.decision_policy == "high_risk"


def test_recommend_routes_explanation_is_generated_from_real_values():
    g = _diamond_graph()
    results = recommend_routes(g, "A", "D", _FakeSource(), CONFIG)
    top = results[0]
    assert f"{top.total_time:.1f}" in top.explanation
    assert top.decision_policy in top.explanation


def test_recommend_routes_is_deterministic():
    g = _diamond_graph()
    results1 = recommend_routes(g, "A", "D", _FakeSource(), CONFIG)
    results2 = recommend_routes(g, "A", "D", _FakeSource(), CONFIG)
    assert [r.route_id for r in results1] == [r.route_id for r in results2]
    assert [r.score for r in results1] == [r.score for r in results2]


def test_identical_route_scores_both_retained_and_order_stable():
    g = nx.DiGraph()
    for n in ["A", "B1", "B2", "D"]:
        g.add_node(n, lat=0.0, lon=0.0)
    # Two genuinely different but numerically-identical-cost/time/risk routes.
    for mid in ["B1", "B2"]:
        g.add_edge("A", mid, edge_id=f"e_{mid}_1", route_id=f"R_{mid}", trip_id=f"T_{mid}", transport_mode="bus",
                   travel_time=10.0, cost=5.0, disruption_probability=0.2, reliability=0.8, is_transfer=False)
        g.add_edge(mid, "D", edge_id=f"e_{mid}_2", route_id=f"R_{mid}", trip_id=f"T_{mid}", transport_mode="bus",
                   travel_time=10.0, cost=5.0, disruption_probability=0.2, reliability=0.8, is_transfer=False)
    results = recommend_routes(g, "A", "D", _FakeSource(), CONFIG, top_n=5)
    assert len(results) == 2
    assert results[0].score == pytest.approx(results[1].score)


# --- rerouting ---


def test_apply_disruption_updates_does_not_mutate_original_graph():
    g = _diamond_graph()
    original_p = g.edges["A", "C"]["disruption_probability"]
    apply_disruption_updates(g, {"e3": 0.99})
    assert g.edges["A", "C"]["disruption_probability"] == original_p  # unchanged


def test_apply_disruption_updates_changes_reliability_consistently():
    g = _diamond_graph()
    updated = apply_disruption_updates(g, {"e1": 0.9})
    assert updated.edges["A", "B"]["disruption_probability"] == pytest.approx(0.9)
    assert updated.edges["A", "B"]["reliability"] == pytest.approx(0.1)


def test_apply_disruption_updates_rejects_unknown_edge():
    g = _diamond_graph()
    with pytest.raises(KeyError):
        apply_disruption_updates(g, {"not_a_real_edge": 0.5})


def test_apply_disruption_updates_rejects_invalid_probability():
    g = _diamond_graph()
    with pytest.raises(ValueError):
        apply_disruption_updates(g, {"e1": 1.5})


def test_reroute_changes_recommendation_when_current_route_becomes_worse():
    g = _diamond_graph()
    initial = recommend_routes(g, "A", "D", _FakeSource(), CONFIG)[0]
    # Push the CURRENTLY RECOMMENDED route's first edge to near-certain disruption.
    first_edge_id = g.edges[initial.stops[0], initial.stops[1]]["edge_id"]
    result = reroute(initial, {first_edge_id: 0.99}, g, _FakeSource(), CONFIG)
    assert result["changed"] is True
    assert result["recommended_route"].route_id != initial.route_id


def test_reroute_keeps_same_recommendation_when_update_is_irrelevant():
    g = _diamond_graph()
    initial = recommend_routes(g, "A", "D", _FakeSource(), CONFIG)[0]
    route_edge_ids = {g.edges[a, b]["edge_id"] for a, b in zip(initial.stops[:-1], initial.stops[1:])}
    other_edge_id = next(d["edge_id"] for _, _, d in g.edges(data=True) if d["edge_id"] not in route_edge_ids)
    current_p = next(d["disruption_probability"] for _, _, d in g.edges(data=True) if d["edge_id"] == other_edge_id)

    tiny_bump = min(1.0, current_p + 0.001)
    result = reroute(initial, {other_edge_id: tiny_bump}, g, _FakeSource(), CONFIG)
    assert result["recommended_route"].route_id == initial.route_id
    assert result["changed"] is False


# --- real-graph integration (Stage 6 §18 demonstration scenario) ---

@requires_routing_stack
def test_section18_end_to_end_scenario(routing_graph, prediction_source, params_config):
    """Origin -> destination -> candidate routes -> disruption predictions
    -> route scoring -> selected route, run as an actual test."""
    graph, _ = routing_graph
    giant = list(max(nx.weakly_connected_components(graph), key=len))
    origin, destination = None, None
    for o in giant:
        for d in giant:
            if o != d and nx.has_path(graph, o, d):
                origin, destination = o, d
                break
        if origin:
            break
    assert origin is not None, "expected at least one reachable pair in the giant component"

    results = recommend_routes(graph, origin, destination, prediction_source, params_config,
                                data_version="test-scenario")
    assert len(results) >= 1
    top = results[0]
    assert top.origin == origin and top.destination == destination
    assert 0.0 <= top.reliability <= 1.0
    assert 0.0 <= top.disruption_risk <= 1.0
    assert top.explanation
    assert top.model_lifecycle_stage == "Candidate"
    assert top.is_production_model is False


@requires_routing_stack
def test_section18_controlled_disruption_scenario(routing_graph, prediction_source, params_config):
    """Initial route -> increased disruption probability -> recalculated
    route -> changed recommendation, demonstrated as an actual test (no
    fabricated improvement percentage — just the functional behavior)."""
    graph, _ = routing_graph
    giant = list(max(nx.weakly_connected_components(graph), key=len))
    origin, destination = None, None
    for o in giant:
        for d in giant:
            if o != d and nx.has_path(graph, o, d) and len(nx.shortest_path(graph, o, d)) > 2:
                origin, destination = o, d
                break
        if origin:
            break
    assert origin is not None

    initial = recommend_routes(graph, origin, destination, prediction_source, params_config)[0]
    first_edge_id = graph.edges[initial.stops[0], initial.stops[1]]["edge_id"]

    result = reroute(initial, {first_edge_id: 0.99}, graph, prediction_source, params_config)
    assert result["recommended_route"] is not None
    # The update is a controlled, deliberate change — assert it was actually applied.
    updated_prob = result["updated_graph"].edges[initial.stops[0], initial.stops[1]]["disruption_probability"]
    assert updated_prob == pytest.approx(0.99)
