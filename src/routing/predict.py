"""Runs the selected disruption-prediction model (see prediction_source.py)
over a feature DataFrame built for graph edges. Handles both model
flavors the same way training/prepare_inputs.py and inference/model_loader.py
already established — no new input-preparation logic invented here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.routing.prediction_source import PredictionSource
from training.prepare_inputs import ALL_FEATURES, build_xgboost_matrix


def predict_disruption_probabilities(
    source: PredictionSource, feature_df: pd.DataFrame, preprocessor=None,
) -> np.ndarray:
    flavor = source.metadata.model_flavor
    if flavor == "xgboost":
        X = build_xgboost_matrix(feature_df)
        return source.model.predict_proba(X)[:, 1]
    if flavor == "sklearn":
        if preprocessor is None:
            raise ValueError("A fitted preprocessor is required to score a 'sklearn' flavor model")
        X = preprocessor.transform(feature_df[ALL_FEATURES])
        return source.model.predict_proba(X)[:, 1]
    raise ValueError(f"Unsupported model flavor '{flavor}' for prediction")
