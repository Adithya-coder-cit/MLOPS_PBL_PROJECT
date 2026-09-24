"""Business logic for POST /predict-disruption. Builds a single-row
feature vector the same way src/routing/graph_builder.py builds one per
edge (reusing the exact same shared utilities — see
build_transfer_lookup / latest_route_history), then calls the actual
loaded model via src/routing/predict.py. No hardcoded predictions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from api.exceptions import UnknownRouteError, UnknownStopError
from src.routing.graph_builder import build_transfer_lookup, latest_route_history
from src.routing.predict import predict_disruption_probabilities
from src.routing.prediction_source import PredictionSource
from src.utils.time_buckets import classify_day_period, time_of_day_bucket


@dataclass
class PredictionResult:
    disruption_probability: float
    predicted_class: int
    decision_threshold: float
    feature_timestamp: datetime
    explanation: str
    top_factors: list[str]


class InferenceService:
    def __init__(
        self, prediction_source: PredictionSource, preprocessor, raw_tables: dict,
        interim_feature_table: pd.DataFrame, synthetic_config: dict, decision_threshold: float,
        feature_importance_dir: Path = Path("models/feature_importance"),
    ):
        self.prediction_source = prediction_source
        self.preprocessor = preprocessor
        self.stops = raw_tables["stops"]
        self.routes = raw_tables["routes"].set_index("route_id")
        self.trips = raw_tables["trips"]
        self.stop_times = raw_tables["stop_times"]
        self.synthetic_config = synthetic_config
        self.decision_threshold = decision_threshold

        self._valid_stop_ids = set(self.stops["stop_id"])
        self._valid_route_ids = set(self.routes.index)
        self._latest_history = latest_route_history(interim_feature_table)
        window = synthetic_config["transfer"]["window_minutes"]
        self._transfer_lookup = build_transfer_lookup(self.stop_times, self.trips, window)

        self._top_factors = self._load_top_factors(feature_importance_dir)

    def _load_top_factors(self, feature_importance_dir: Path, n: int = 5) -> list[str]:
        flavor = self.prediction_source.metadata.model_flavor
        filename = "xgboost_importance.json" if flavor == "xgboost" else "random_forest_importance.json"
        path = feature_importance_dir / filename
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [r["feature"].split("__")[-1] for r in data.get("top_features", [])[:n]]

    def _find_trip_id(self, route_id: str, stop_id: str) -> str | None:
        route_trip_ids = set(self.trips.loc[self.trips["route_id"] == route_id, "trip_id"])
        matches = self.stop_times[
            self.stop_times["trip_id"].isin(route_trip_ids) & (self.stop_times["stop_id"] == stop_id)
        ]
        return matches["trip_id"].iloc[0] if len(matches) else None

    def predict(
        self, route_id: str, stop_id: str, query_datetime: datetime,
        precipitation_mm: float, temperature_c: float, visibility_km: float,
    ) -> PredictionResult:
        if route_id not in self._valid_route_ids:
            raise UnknownRouteError(route_id)
        if stop_id not in self._valid_stop_ids:
            raise UnknownStopError(stop_id)

        transport_mode = self.routes.loc[route_id, "transport_mode"]
        trip_id = self._find_trip_id(route_id, stop_id)
        transfer_dependency = (
            self._transfer_lookup.get((trip_id, stop_id), 0) if trip_id is not None else 0
        )
        hist = self._latest_history.loc[route_id] if route_id in self._latest_history.index else None

        minute_of_day = query_datetime.hour * 60 + query_datetime.minute
        dp_cfg = self.synthetic_config["day_periods"]
        day_period = classify_day_period(minute_of_day, dp_cfg["peak_windows"], dp_cfg["night_window"])

        feature_df = pd.DataFrame([{
            "transport_mode": transport_mode, "day_period": day_period,
            "time_of_day_bucket": time_of_day_bucket(query_datetime.hour),
            "hour": query_datetime.hour, "day_of_week": query_datetime.weekday(),
            "is_weekend": int(query_datetime.weekday() >= 5),
            "precipitation_mm": precipitation_mm, "temperature_c": temperature_c, "visibility_km": visibility_km,
            "transfer_dependency": transfer_dependency,
            "historical_delay_minutes": hist["historical_delay_minutes"] if hist is not None else None,
            "rolling_7d_delay_minutes": hist["rolling_7d_delay_minutes"] if hist is not None else None,
            "historical_reliability": hist["historical_reliability"] if hist is not None else None,
        }])

        probability = float(predict_disruption_probabilities(self.prediction_source, feature_df,
                                                               preprocessor=self.preprocessor)[0])
        predicted_class = int(probability >= self.decision_threshold)

        explanation = (
            f"Predicted disruption probability {probability * 100:.1f}% for route {route_id} at stop {stop_id} "
            f"({transport_mode}, {day_period}, transfer_dependency={transfer_dependency}) "
            f"under weather precipitation={precipitation_mm}mm, temperature={temperature_c}C, "
            f"visibility={visibility_km}km. Classified as "
            f"{'disruption' if predicted_class else 'no disruption'} at threshold {self.decision_threshold}."
        )

        return PredictionResult(
            disruption_probability=probability, predicted_class=predicted_class,
            decision_threshold=self.decision_threshold, feature_timestamp=query_datetime,
            explanation=explanation, top_factors=self._top_factors,
        )
