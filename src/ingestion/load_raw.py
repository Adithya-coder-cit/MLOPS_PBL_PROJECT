"""Load the raw RouteWise tables (DVC-tracked CSVs under data/raw/) with
explicit dtypes. This is the single place that knows the raw file layout —
both validation and the feature pipeline load through here so they never
drift apart.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")


def load_raw_tables(raw_dir: Path = RAW_DIR) -> dict[str, pd.DataFrame]:
    tables = {
        "stops": pd.read_csv(raw_dir / "gtfs" / "stops.csv"),
        "routes": pd.read_csv(raw_dir / "gtfs" / "routes.csv"),
        "trips": pd.read_csv(raw_dir / "gtfs" / "trips.csv"),
        "stop_times": pd.read_csv(raw_dir / "gtfs" / "stop_times.csv"),
        "fares": pd.read_csv(raw_dir / "gtfs" / "fares.csv"),
        "historical_operational_records": pd.read_csv(
            raw_dir / "operational" / "historical_operational_records.csv"
        ),
        "weather_observations": pd.read_csv(raw_dir / "weather" / "weather_observations.csv"),
    }
    return tables
