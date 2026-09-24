"""Top-level routing orchestrator: candidate generation -> aggregation ->
per-candidate adaptive weighting -> cross-candidate normalization ->
scoring -> ranking -> explanation -> RouteResult.

Adaptive weighting is applied PER CANDIDATE, using that candidate's own
aggregate disruption_risk — a riskier candidate gets its OWN reliability
weighted more heavily in its OWN score (see
decision_engine/adaptive_weighting.py). Normalization is then applied
ACROSS the candidate set (see decision_engine/normalization.py), which
is why generation and normalization happen before scoring, not per-edge.
"""
from __future__ import annotations

import networkx as nx

from src.decision_engine.adaptive_weighting import select_weights
from src.decision_engine.explanation import generate_explanation
from src.decision_engine.normalization import normalize_candidates
from src.decision_engine.scoring import compute_score
from src.routing.candidates import generate_candidate_paths
from src.routing.path_aggregation import aggregate_path
from src.routing.path_search import NoPathFoundError
from src.routing.prediction_source import PredictionSource
from src.routing.route_result import RouteResult, make_route_id


class UnreachableDestinationError(Exception):
    pass


def recommend_routes(
    graph: nx.DiGraph, origin: str, destination: str, prediction_source: PredictionSource,
    config: dict, data_version: str | None = None, top_n: int = 3,
) -> list[RouteResult]:
    if origin not in graph:
        raise NoPathFoundError(f"Origin stop '{origin}' is not in the graph")
    if destination not in graph:
        raise NoPathFoundError(f"Destination stop '{destination}' is not in the graph")

    raw_paths = generate_candidate_paths(graph, origin, destination, config)
    if not raw_paths:
        raise UnreachableDestinationError(f"No route exists from {origin} to {destination}")

    transfer_config = config["routing"]["transfer_penalty"]
    aggregated = [aggregate_path(graph, path, transfer_config) for path in raw_paths]

    weights_and_policy = [select_weights(a["disruption_risk"], config["decision_engine"]) for a in aggregated]

    norm_costs, norm_times, norm_reliabilities = normalize_candidates(
        [a["total_cost"] for a in aggregated], [a["total_time"] for a in aggregated],
        [a["reliability"] for a in aggregated], config["routing"]["normalization"],
    )

    scored = []
    for a, (weights, policy), c, t, r in zip(aggregated, weights_and_policy, norm_costs, norm_times,
                                              norm_reliabilities):
        score = compute_score(c, t, r, weights)
        scored.append({**a, "score": score, "decision_policy": policy})

    scored.sort(key=lambda a: a["score"])
    top = scored[:top_n]

    source_desc = prediction_source.describe()
    results = []
    for i, candidate in enumerate(top):
        explanation = (
            generate_explanation(candidate, top, candidate["decision_policy"])
            if i == 0 else
            (f"Alternative route ({candidate['decision_policy']} policy): "
             f"{candidate['total_time']:.1f} min, cost {candidate['total_cost']:.2f}, "
             f"reliability {candidate['reliability'] * 100:.1f}%, "
             f"{candidate['transfer_count']} transfer(s) via {'/'.join(candidate['transport_modes'])}.")
        )
        results.append(RouteResult(
            route_id=make_route_id(origin, destination, candidate["path"]),
            origin=origin, destination=destination,
            transport_modes=candidate["transport_modes"], stops=candidate["path"],
            segments=candidate["segments"], total_time=candidate["total_time"],
            total_cost=candidate["total_cost"], reliability=candidate["reliability"],
            disruption_risk=candidate["disruption_risk"], transfer_count=candidate["transfer_count"],
            score=candidate["score"], decision_policy=candidate["decision_policy"],
            model_version=source_desc["model_version"], model_lifecycle_stage=source_desc["lifecycle_stage"],
            is_production_model=source_desc["is_production"], data_version=data_version,
            explanation=explanation, model_source_warning=source_desc["warning"],
        ))
    return results
