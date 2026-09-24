"""Build model-specific input matrices from the processed feature table.

Two deliberately different strategies for missing values (Stage 4 §2):

A. XGBoost — native missing-value handling. Numeric features are passed
   through with NaN preserved; categoricals are cast to pandas 'category'
   dtype and XGBoost (enable_categorical=True, tree_method='hist') learns
   the optimal split direction for missing values itself. No imputation.

B. Random Forest — sklearn's RandomForestClassifier cannot accept NaN, so
   it consumes the Stage 3 preprocessor.joblib output (median-impute +
   scale numeric, one-hot categorical), fit only on train in Stage 3.
   Reused here unchanged — never refit on val/test.
"""
from __future__ import annotations

import pandas as pd

from src.preprocessing.pipeline import CATEGORICAL_FEATURES, NUMERIC_FEATURES

ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def build_xgboost_matrix(df: pd.DataFrame) -> pd.DataFrame:
    X = df[ALL_FEATURES].copy()
    for col in CATEGORICAL_FEATURES:
        X[col] = X[col].astype("category")
    return X


def build_random_forest_matrix(df: pd.DataFrame, preprocessor) -> pd.DataFrame | object:
    return preprocessor.transform(df[ALL_FEATURES])


def get_target(df: pd.DataFrame, target_column: str = "disruption_flag") -> pd.Series:
    return df[target_column].astype(int)
