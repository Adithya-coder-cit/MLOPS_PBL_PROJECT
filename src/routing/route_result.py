"""The structured route result schema (Stage 6 §15) — this will become
the FastAPI response contract in a later stage, so its shape is treated
as a stable contract already.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class RouteResult:
    route_id: str
    origin: str
    destination: str
    transport_modes: list[str]
    stops: list[str]
    segments: list[dict]
    total_time: float
    total_cost: float
    reliability: float
    disruption_risk: float
    transfer_count: int
    score: float
    decision_policy: str
    model_version: str
    model_lifecycle_stage: str | None
    is_production_model: bool
    data_version: str | None
    explanation: str
    model_source_warning: str | None = field(default=None)

    def to_dict(self) -> dict:
        return {
            "route_id": self.route_id, "origin": self.origin, "destination": self.destination,
            "transport_modes": self.transport_modes, "stops": self.stops, "segments": self.segments,
            "total_time": self.total_time, "total_cost": self.total_cost, "reliability": self.reliability,
            "disruption_risk": self.disruption_risk, "transfer_count": self.transfer_count,
            "score": self.score, "decision_policy": self.decision_policy,
            "model_version": self.model_version, "model_lifecycle_stage": self.model_lifecycle_stage,
            "is_production_model": self.is_production_model, "data_version": self.data_version,
            "explanation": self.explanation, "model_source_warning": self.model_source_warning,
        }


def make_route_id(origin: str, destination: str, stops: list[str]) -> str:
    digest = hashlib.sha256("|".join(stops).encode()).hexdigest()[:8]
    return f"{origin}-{destination}-{digest}"
