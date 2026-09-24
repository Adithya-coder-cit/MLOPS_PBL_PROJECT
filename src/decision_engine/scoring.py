"""Score = alpha*C + beta*T - gamma*R, lower is better.

Sign convention, verified: C (normalized cost) and T (normalized time)
are "bad" — a route becomes worse as either increases, so they're added
positively. R (normalized reliability) is "good" — a route becomes
better as it increases, so it's SUBTRACTED, making higher reliability
pull the score down (better). This makes minimizing Score simultaneously
minimize cost and time while maximizing reliability, which is the
intended multi-objective trade-off. See
tests/test_decision_engine.py::test_score_sign_convention_monotonicity
for a direct monotonicity proof, not just an assertion here.
"""
from __future__ import annotations

from src.decision_engine.adaptive_weighting import Weights


def compute_score(normalized_cost: float, normalized_time: float, normalized_reliability: float,
                   weights: Weights) -> float:
    if weights.alpha < 0 or weights.beta < 0 or weights.gamma < 0:
        raise ValueError(f"Score weights must be non-negative, got {weights}")
    return weights.alpha * normalized_cost + weights.beta * normalized_time - weights.gamma * normalized_reliability
