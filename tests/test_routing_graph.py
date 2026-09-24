"""Tests for graph construction, edge attributes, and source-data
lineage, against the REAL routing graph built from the Stage 2/3
development dataset (never a hardcoded/unrelated graph)."""
from tests.conftest import requires_routing_stack

REQUIRED_EDGE_ATTRS = {
    "travel_time", "cost", "transport_mode", "disruption_probability",
    "reliability", "route_id", "trip_id", "is_transfer",
}


@requires_routing_stack
def test_graph_has_nodes_from_real_stops_data(routing_graph):
    import pandas as pd
    graph, _ = routing_graph
    stops = pd.read_csv("data/raw/gtfs/stops.csv")
    assert graph.number_of_nodes() == len(stops)
    assert set(graph.nodes) == set(stops["stop_id"])


@requires_routing_stack
def test_graph_edges_have_all_required_attributes(routing_graph):
    graph, _ = routing_graph
    assert graph.number_of_edges() > 0
    for _, _, data in graph.edges(data=True):
        assert REQUIRED_EDGE_ATTRS <= set(data.keys())


@requires_routing_stack
def test_graph_edge_values_are_well_formed(routing_graph):
    graph, _ = routing_graph
    for _, _, data in graph.edges(data=True):
        # >= 0, not > 0: a handful of very short legs round to travel_time==0
        # at minute granularity (GTFS-style HH:MM:SS scheduling) — a real,
        # documented data property (see test_zero_travel_time_edge_is_a_real_
        # documented_artifact below), not a graph-construction bug.
        assert data["travel_time"] >= 0
        assert data["cost"] >= 0
        assert 0.0 <= data["disruption_probability"] <= 1.0
        assert 0.0 <= data["reliability"] <= 1.0
        assert abs(data["reliability"] - (1 - data["disruption_probability"])) < 1e-9


@requires_routing_stack
def test_zero_travel_time_edge_is_a_real_documented_artifact(routing_graph):
    """Confirms the zero/near-zero-time edge case the Stage 6 brief asks
    to test for: at minute-granularity scheduling, a very short leg's
    independently-rounded arrival/departure can produce travel_time==0.
    This is a genuine property of the source data — not injected here —
    and must not break path search/aggregation (see test_path_search.py /
    test_path_aggregation.py, which exercise zero-weight edges directly).
    """
    graph, _ = routing_graph
    zero_time_edges = [(u, v, d) for u, v, d in graph.edges(data=True) if d["travel_time"] == 0]
    assert len(zero_time_edges) >= 1  # at least one such edge really exists in this dataset
    for u, v, d in zero_time_edges:
        assert d["cost"] >= 0  # still a valid, usable edge otherwise
        assert 0.0 <= d["reliability"] <= 1.0


@requires_routing_stack
def test_graph_represents_multiple_transport_modes(routing_graph):
    graph, _ = routing_graph
    modes = {d["transport_mode"] for _, _, d in graph.edges(data=True)}
    assert modes == {"bus", "tram", "metro", "rail", "ferry"}


@requires_routing_stack
def test_graph_edge_count_matches_representative_trips_times_legs(routing_graph):
    import pandas as pd
    graph, _ = routing_graph
    trips = pd.read_csv("data/raw/gtfs/trips.csv")
    n_route_directions = trips.groupby(["route_id", "direction_id"]).ngroups
    # Each representative trip contributes (n_stops_in_trip - 1) edges; just
    # sanity-check the edge count is in a plausible range, not an exact
    # formula (varies per route's stop count).
    assert graph.number_of_edges() >= n_route_directions  # at least 1 leg each


@requires_routing_stack
def test_every_edge_has_lineage(routing_graph):
    graph, lineage = routing_graph
    for _, _, data in graph.edges(data=True):
        assert data["edge_id"] in lineage
        entry = lineage[data["edge_id"]]
        field_names = {f.value_name for f in entry.fields}
        assert {"travel_time", "cost", "disruption_probability", "reliability"} <= field_names


@requires_routing_stack
def test_lineage_marks_derived_vs_sourced_correctly(routing_graph):
    graph, lineage = routing_graph
    any_edge_id = next(iter(lineage))
    entry = lineage[any_edge_id]
    by_name = {f.value_name: f for f in entry.fields}
    assert by_name["travel_time"].is_derived is False  # directly from stop_times scheduled times
    assert by_name["cost"].is_derived is True  # apportioned from a route-level fare
    assert by_name["disruption_probability"].is_derived is True  # model output
    assert by_name["reliability"].is_derived is True  # 1 - p


@requires_routing_stack
def test_lineage_source_records_are_traceable(routing_graph):
    graph, lineage = routing_graph
    for entry in list(lineage.values())[:5]:
        for f in entry.fields:
            assert f.source_dataset  # non-empty
            assert f.source_record  # non-empty
            assert f.transformation  # non-empty


@requires_routing_stack
def test_graph_has_disconnected_stops_reflecting_real_data(routing_graph):
    """Not every stop in the synthetic dataset is served by a route —
    this must show up honestly as isolated nodes, not be hidden."""
    graph, _ = routing_graph
    isolated = [n for n in graph.nodes if graph.degree(n) == 0]
    assert len(isolated) > 0


@requires_routing_stack
def test_single_mode_routes_remain_valid(routing_graph):
    """Section 11: single-mode routes must remain valid — not every path
    is forced to be multi-modal. Finds a route with >=2 consecutive legs
    and confirms following it end-to-end is a single-transport_mode path."""
    from src.routing.path_aggregation import aggregate_path

    graph, _ = routing_graph
    by_route: dict[str, list[tuple[str, str]]] = {}
    for u, v, d in graph.edges(data=True):
        by_route.setdefault(d["route_id"], []).append((u, v))

    multi_leg_route = next(route_id for route_id, edges in by_route.items() if len(edges) >= 2)
    edges = by_route[multi_leg_route]
    path = [edges[0][0], edges[0][1], edges[1][1]] if edges[0][1] == edges[1][0] else [edges[0][0], edges[0][1]]

    result = aggregate_path(graph, path, {"time_minutes": 5.0, "cost": 2.0, "reliability_penalty": 0.02})
    assert len(result["transport_modes"]) == 1
    assert result["transfer_count"] == 0
