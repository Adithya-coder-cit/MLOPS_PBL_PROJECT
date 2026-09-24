"""Tests for reliability, normalization, scoring, and adaptive weighting
— all pure functions, no graph or model required."""
import math

import pytest

from src.decision_engine.adaptive_weighting import Weights, select_weights
from src.decision_engine.normalization import fixed_bounds_normalize, minmax_normalize, normalize_candidates
from src.decision_engine.reliability import (
    edge_reliability,
    reliability_to_dijkstra_weight,
    route_disruption_risk,
    route_reliability,
)
from src.decision_engine.scoring import compute_score

# --- reliability ---


def test_edge_reliability_is_complement_of_disruption_probability():
    assert edge_reliability(0.3) == pytest.approx(0.7)
    assert edge_reliability(0.0) == pytest.approx(1.0)
    assert edge_reliability(1.0) == pytest.approx(0.0)


def test_edge_reliability_rejects_out_of_range():
    with pytest.raises(ValueError):
        edge_reliability(1.5)
    with pytest.raises(ValueError):
        edge_reliability(-0.1)


def test_route_reliability_is_product_of_edge_reliabilities():
    result = route_reliability([0.1, 0.2, 0.0])
    expected = 0.9 * 0.8 * 1.0
    assert result == pytest.approx(expected)


def test_route_reliability_empty_route_is_fully_reliable():
    assert route_reliability([]) == pytest.approx(1.0)


def test_route_disruption_risk_is_complement_of_route_reliability():
    probs = [0.1, 0.2]
    assert route_disruption_risk(probs) == pytest.approx(1 - route_reliability(probs))


def test_reliability_to_dijkstra_weight_matches_log_transform():
    assert reliability_to_dijkstra_weight(0.5) == pytest.approx(-math.log(0.5))
    # Chaining: sum of -log(r_i) == -log(prod(r_i))
    r1, r2 = 0.8, 0.6
    summed = reliability_to_dijkstra_weight(r1) + reliability_to_dijkstra_weight(r2)
    assert summed == pytest.approx(-math.log(r1 * r2))


def test_reliability_to_dijkstra_weight_handles_zero_reliability():
    # Must not raise (log(0) is undefined) — floored instead.
    w = reliability_to_dijkstra_weight(0.0)
    assert w > 0 and math.isfinite(w)


# --- normalization ---


def test_minmax_normalize_maps_to_unit_range():
    result = minmax_normalize([10, 20, 30])
    assert result[0] == pytest.approx(0.0)
    assert result[-1] == pytest.approx(1.0)
    assert result[1] == pytest.approx(0.5)


def test_minmax_normalize_degenerate_equal_values():
    result = minmax_normalize([5, 5, 5])
    assert result == [0.5, 0.5, 0.5]


def test_fixed_bounds_normalize_clips_out_of_range():
    result = fixed_bounds_normalize([-10, 50, 200], {"min": 0, "max": 100})
    assert result[0] == pytest.approx(0.0)  # clipped
    assert result[1] == pytest.approx(0.5)
    assert result[2] == pytest.approx(1.0)  # clipped


def test_normalize_candidates_uses_minmax_with_multiple_candidates():
    config = {"method": "minmax_candidates", "fixed_bounds": {
        "cost": {"min": 0, "max": 100}, "time_minutes": {"min": 0, "max": 100}, "reliability": {"min": 0, "max": 1},
    }}
    costs, times, rels = normalize_candidates([10, 20], [5, 15], [0.5, 0.9], config)
    assert costs == pytest.approx([0.0, 1.0])


def test_normalize_candidates_falls_back_to_fixed_bounds_for_single_candidate():
    config = {"method": "minmax_candidates", "fixed_bounds": {
        "cost": {"min": 0, "max": 100}, "time_minutes": {"min": 0, "max": 200}, "reliability": {"min": 0, "max": 1},
    }}
    costs, times, rels = normalize_candidates([50], [100], [0.5], config)
    assert costs == pytest.approx([0.5])
    assert times == pytest.approx([0.5])


# --- scoring: sign convention ---


def test_score_sign_convention_monotonicity():
    """Verifies: increasing cost or time (holding others fixed) increases
    score; increasing reliability decreases score. This is the direct
    proof that lower-is-better is mathematically consistent with the
    formula's signs."""
    w = Weights(alpha=1.0, beta=1.0, gamma=1.0)
    base = compute_score(0.3, 0.3, 0.5, w)

    higher_cost = compute_score(0.6, 0.3, 0.5, w)
    assert higher_cost > base

    higher_time = compute_score(0.3, 0.6, 0.5, w)
    assert higher_time > base

    higher_reliability = compute_score(0.3, 0.3, 0.9, w)
    assert higher_reliability < base


def test_score_rejects_negative_weights():
    with pytest.raises(ValueError):
        compute_score(0.5, 0.5, 0.5, Weights(alpha=-1, beta=0.5, gamma=0.5))


def test_score_is_deterministic():
    w = Weights(alpha=0.34, beta=0.33, gamma=0.33)
    s1 = compute_score(0.4, 0.6, 0.7, w)
    s2 = compute_score(0.4, 0.6, 0.7, w)
    assert s1 == s2


# --- adaptive weighting ---

GATE_CONFIG = {
    "baseline_weights": {"alpha": 0.34, "beta": 0.33, "gamma": 0.33},
    "high_risk_threshold": 0.4,
    "high_risk_weights": {"alpha": 0.27, "beta": 0.23, "gamma": 0.5},
}


def test_select_weights_uses_baseline_below_threshold():
    weights, policy = select_weights(0.1, GATE_CONFIG)
    assert policy == "baseline"
    assert weights.gamma == pytest.approx(0.33)


def test_select_weights_switches_to_high_risk_above_threshold():
    weights, policy = select_weights(0.5, GATE_CONFIG)
    assert policy == "high_risk"
    assert weights.gamma == pytest.approx(0.5)
    assert weights.gamma > GATE_CONFIG["baseline_weights"]["gamma"]  # reliability weighted MORE under high risk


def test_select_weights_transition_is_deterministic_at_threshold():
    # exactly at threshold -> baseline (not > threshold)
    weights, policy = select_weights(0.4, GATE_CONFIG)
    assert policy == "baseline"
    # just above -> high_risk
    weights, policy = select_weights(0.4001, GATE_CONFIG)
    assert policy == "high_risk"
