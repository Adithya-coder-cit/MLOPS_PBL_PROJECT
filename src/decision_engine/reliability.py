"""Reliability definition, kept single and consistent across the project.

Per-edge: reliability = 1 - disruption_probability. disruption_probability
comes directly from the trained classifier's predict_proba (already in
[0,1] by construction), so reliability is also always in [0,1] and moves
inversely with risk — this is the only definition of "reliability" used
anywhere in RouteWise (see also configs/synthetic_data.yaml's generative
process and training/evaluate.py, which never define it any other way).

Route-level: a route is a chain of independent-ish legs, so its overall
"no disruption anywhere on this route" probability is the PRODUCT of
each leg's reliability (standard series-reliability composition, under
an explicit independence assumption — documented, not fabricated).
Route disruption risk = 1 - route_reliability, the complementary event.
"""
from __future__ import annotations

import math

import numpy as np


def edge_reliability(disruption_probability: float) -> float:
    if not 0.0 <= disruption_probability <= 1.0:
        raise ValueError(f"disruption_probability must be in [0,1], got {disruption_probability}")
    return 1.0 - disruption_probability


def route_reliability(edge_disruption_probabilities: list[float]) -> float:
    """Product of per-edge reliabilities, assuming independence across
    legs. An empty route (origin == destination, zero edges) is
    trivially fully reliable.
    """
    reliability = 1.0
    for p in edge_disruption_probabilities:
        reliability *= edge_reliability(p)
    return reliability


def route_disruption_risk(edge_disruption_probabilities: list[float]) -> float:
    return 1.0 - route_reliability(edge_disruption_probabilities)


def reliability_to_dijkstra_weight(reliability: float, floor: float = 1e-6) -> float:
    """Converts a MULTIPLICATIVE reliability chain into an ADDITIVE
    Dijkstra-compatible edge weight: minimizing sum(-log(r_i)) is
    equivalent to maximizing prod(r_i) = maximizing route reliability
    (minimizing risk). Standard log-transform trick for chaining
    probabilities through a shortest-path search. `floor` avoids -log(0).
    """
    return -math.log(max(reliability, floor))


def is_probability_vector_valid(values: np.ndarray) -> bool:
    return bool(np.all((values >= 0.0) & (values <= 1.0)))
