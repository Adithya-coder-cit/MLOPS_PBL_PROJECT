"""Business logic for POST /recommend-route and POST /reroute. Wraps the
EXISTING Stage 6 routing engine (src/routing/engine.py,
src/routing/rerouting.py) — no route-scoring logic is duplicated here.
"""
from __future__ import annotations

from datetime import datetime

import networkx as nx

from api.exceptions import UnknownStopError
from src.routing.engine import recommend_routes
from src.routing.rerouting import reroute
from src.routing.route_result import RouteResult


def route_result_to_schema(result: RouteResult) -> dict:
    return {
        "route_id": result.route_id, "origin": result.origin, "destination": result.destination,
        "transport_modes": result.transport_modes, "stops": result.stops, "segments": result.segments,
        "total_time": result.total_time, "total_cost": result.total_cost, "reliability": result.reliability,
        "disruption_risk": result.disruption_risk, "transfer_count": result.transfer_count,
        "score": result.score, "decision_policy": result.decision_policy, "data_version": result.data_version,
        "explanation": result.explanation,
        "model_metadata": {
            "model_name": "RouteWise-Disruption-Model", "model_version": result.model_version,
            "lifecycle_stage": result.model_lifecycle_stage, "is_production_model": result.is_production_model,
            "model_source_warning": result.model_source_warning,
        },
    }


class RoutingService:
    def __init__(self, graph: nx.DiGraph, prediction_source, config: dict, data_version: str | None):
        self.graph = graph
        self.prediction_source = prediction_source
        self.config = config
        self.data_version = data_version

    def _validate_stop(self, stop_id: str) -> None:
        if stop_id not in self.graph:
            raise UnknownStopError(stop_id)

    def recommend(self, origin: str, destination: str, top_n: int = 3,
                  departure_time: datetime | None = None) -> list[dict]:
        self._validate_stop(origin)
        self._validate_stop(destination)
        results = recommend_routes(
            self.graph, origin, destination, self.prediction_source, self.config,
            data_version=self.data_version, top_n=top_n,
        )
        return [route_result_to_schema(r) for r in results]

    def reroute(self, origin: str, destination: str, edge_updates: dict[str, float], top_n: int = 3) -> dict:
        self._validate_stop(origin)
        self._validate_stop(destination)

        original_results = recommend_routes(
            self.graph, origin, destination, self.prediction_source, self.config,
            data_version=self.data_version, top_n=top_n,
        )
        original = original_results[0]

        result = reroute(original, edge_updates, self.graph, self.prediction_source, self.config,
                          data_version=self.data_version)
        updated = result["recommended_route"]

        if result["changed"]:
            reason = (
                f"Recommendation changed from route {original.route_id} to {updated.route_id}: "
                f"disruption risk moved from {original.disruption_risk * 100:.1f}% to "
                f"{updated.disruption_risk * 100:.1f}%, score from {original.score:.4f} to {updated.score:.4f} "
                f"under the '{updated.decision_policy}' policy."
            )
        else:
            reason = (
                f"Recommendation unchanged (route {original.route_id}) - still the best-scoring candidate "
                f"under the '{updated.decision_policy}' policy after applying the supplied update."
            )

        return {
            "original_route": route_result_to_schema(original),
            "updated_route": route_result_to_schema(updated),
            "changed": result["changed"],
            "old_risk": original.disruption_risk, "new_risk": updated.disruption_risk,
            "old_score": original.score, "new_score": updated.score,
            "reason": reason,
        }
