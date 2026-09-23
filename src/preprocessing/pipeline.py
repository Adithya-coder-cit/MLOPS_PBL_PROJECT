"""sklearn-compatible preprocessing pipeline: median-impute + scale numeric
features, one-hot encode categoricals. MUST be fit only on the train split
(see src/features/build_dataset.py) and applied unchanged to val/test —
fitting on val/test would leak their distribution into the transform.

The fitted transformer is persisted (data/processed/preprocessor.joblib)
for the training stage to reuse; the interpretable engineered-feature
values in train/val/test parquet are kept un-transformed (not one-hot
encoded) so they stay human-readable and reusable by any model type.
"""
from __future__ import annotations

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

NUMERIC_FEATURES = [
    "precipitation_mm", "temperature_c", "visibility_km",
    "historical_delay_minutes", "rolling_7d_delay_minutes", "historical_reliability",
    "transfer_dependency", "hour", "day_of_week",
]
CATEGORICAL_FEATURES = ["transport_mode", "day_period", "time_of_day_bucket"]


def build_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer([
        ("numeric", numeric_pipeline, NUMERIC_FEATURES),
        ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
    ])
