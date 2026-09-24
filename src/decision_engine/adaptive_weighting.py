"""Adaptive weighting policy: reliability's importance (gamma) increases
when a route's disruption risk crosses a configured threshold.

This is a DETERMINISTIC, CONFIGURABLE DECISION POLICY — a documented
if/else switch between two hand-chosen weight sets, not a learned or
scientifically derived function of risk. See params.yaml
decision_engine.{baseline_weights, high_risk_threshold, high_risk_weights}.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Weights:
    alpha: float
    beta: float
    gamma: float

    def to_dict(self) -> dict:
        return {"alpha": self.alpha, "beta": self.beta, "gamma": self.gamma}


def select_weights(route_disruption_risk: float, config: dict) -> tuple[Weights, str]:
    """Returns (weights, policy_label). policy_label is either
    "baseline" or "high_risk" — always explicit, never implicit, so a
    RouteResult can state exactly which policy scored it.
    """
    threshold = config["high_risk_threshold"]
    if route_disruption_risk > threshold:
        w = config["high_risk_weights"]
        return Weights(w["alpha"], w["beta"], w["gamma"]), "high_risk"
    w = config["baseline_weights"]
    return Weights(w["alpha"], w["beta"], w["gamma"]), "baseline"
