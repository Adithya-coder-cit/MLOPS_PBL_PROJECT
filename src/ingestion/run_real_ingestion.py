"""Stage 11B orchestrator: INGEST -> NORMALIZE -> VALIDATE -> EDA ->
FEATURE AVAILABILITY -> MODEL READINESS DECISION.

Deliberately does NOT retrain, register, or promote any model (Stage
11B §23) -- it stops after producing the reports a human uses to decide
whether Stage 12 (real feature-pipeline integration + retraining) should
proceed.

By default this reuses the raw files already downloaded under
data/raw/real/ (see docs -- Stage 11B downloaded and verified these
against the real MBTA feeds) rather than re-downloading on every run;
pass --download to fetch fresh copies first.

Run: python -m src.ingestion.run_real_ingestion
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
from pathlib import Path

import pandas as pd
import yaml

from src.ingestion.gtfs.normalize import (
    build_service_calendar,
    normalize_fares,
    normalize_routes,
    normalize_stop_times,
    normalize_stops,
    normalize_trips,
)
from src.ingestion.gtfs.parser import parse_gtfs_zip
from src.ingestion.gtfs.validator import run_gtfs_validation
from src.ingestion.historical.mbta_lamp import load_bus_events, load_subway_performance
from src.ingestion.historical.normalize import normalize_bus_events, normalize_subway_performance
from src.ingestion.weather.normalize import assign_weather_zone, join_weather_asof

logger = logging.getLogger("routewise.ingestion.run_real_ingestion")

RAW_REAL_DIR = Path("data/raw/real")
OUT_DIR = Path("data/interim/real")
CONFIG_PATH = Path("configs/real_data.yaml")


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def ingest_and_normalize(cfg: dict) -> dict[str, pd.DataFrame]:
    logger.info("Parsing real GTFS feed")
    gtfs_tables = parse_gtfs_zip(RAW_REAL_DIR / "gtfs" / "MBTA_GTFS.zip")

    stops = normalize_stops(gtfs_tables["stops"])
    routes, mode_issues = normalize_routes(gtfs_tables["routes"], cfg["mode_mapping"])
    for issue in mode_issues:
        logger.warning("Mode mapping issue: %s", issue.to_dict())
    trips = normalize_trips(gtfs_tables["trips"])
    stop_times = normalize_stop_times(gtfs_tables["stop_times"])
    service_calendar = build_service_calendar(gtfs_tables.get("calendar"), gtfs_tables.get("calendar_dates"))
    fares = normalize_fares(gtfs_tables.get("fare_products"), gtfs_tables.get("fare_leg_rules"), routes)

    route_to_mode = dict(zip(routes["route_id"], routes["transport_mode"]))

    logger.info("Loading + normalizing real historical performance data")
    subway_files = sorted(glob.glob(str(RAW_REAL_DIR / "historical" / "subway" / "*.parquet")))
    subway_raw = load_subway_performance([Path(f) for f in subway_files])
    subway_events = normalize_subway_performance(subway_raw, route_to_mode, cfg["label_availability"])

    bus_path = RAW_REAL_DIR / "historical" / "bus" / "LAMP_RECENT_Bus_Events.parquet"
    bus_events = pd.DataFrame()
    if bus_path.exists():
        bus_raw = load_bus_events(bus_path)
        bus_events = normalize_bus_events(bus_raw, route_to_mode, cfg["label_availability"])

    operational_events = pd.concat([subway_events, bus_events], ignore_index=True)

    weather_path = RAW_REAL_DIR / "weather" / "KBOS_observations.parquet"
    weather = pd.read_parquet(weather_path) if weather_path.exists() else pd.DataFrame()
    stops_z = assign_weather_zone(stops, cfg["sources"]["weather"]["station"])
    if not weather.empty:
        operational_events = join_weather_asof(
            operational_events, weather, stops_z, cfg["weather_join"]["max_time_difference_hours"],
        )

    return {
        "stops": stops, "routes": routes, "trips": trips, "stop_times": stop_times,
        "service_calendar": service_calendar, "fares": fares,
        "operational_events": operational_events, "weather": weather, "mode_issues": mode_issues,
    }


def write_canonical_tables(tables: dict[str, pd.DataFrame]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in ["stops", "routes", "trips", "stop_times", "service_calendar", "fares", "operational_events",
                 "weather"]:
        df = tables[name]
        if df is None or df.empty:
            logger.warning("Table '%s' is empty -- writing an empty Parquet file, not skipping.", name)
        df.to_parquet(OUT_DIR / f"{name}.parquet", index=False)
    logger.info("Wrote canonical real-data tables to %s", OUT_DIR)


def run_validation(tables: dict[str, pd.DataFrame]) -> list:
    return run_gtfs_validation(
        tables["stops"], tables["routes"], tables["trips"], tables["stop_times"], tables["service_calendar"],
    )


def main(skip_download: bool = True) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    cfg = load_config()

    tables = ingest_and_normalize(cfg)
    write_canonical_tables(tables)

    issues = run_validation(tables)
    errors = [i for i in issues if i.level == "ERROR"]
    logger.info("Validation: %d issue(s), %d error(s)", len(issues), len(errors))

    from src.ingestion.data_quality_report import build_data_quality_report
    from src.ingestion.eda import build_eda_report
    from src.ingestion.feature_availability import build_feature_availability_matrix
    from src.ingestion.model_readiness import build_model_readiness_decision

    dq_report = build_data_quality_report(tables, issues, cfg)
    (OUT_DIR / "data_quality_report.json").write_text(json.dumps(dq_report, indent=2, default=str), encoding="utf-8")

    eda_report = build_eda_report(tables, cfg)
    (OUT_DIR / "eda_report.json").write_text(json.dumps(eda_report, indent=2, default=str), encoding="utf-8")

    feature_matrix = build_feature_availability_matrix(tables, cfg)
    (OUT_DIR / "feature_availability_matrix.json").write_text(json.dumps(feature_matrix, indent=2), encoding="utf-8")

    readiness = build_model_readiness_decision(tables, issues, feature_matrix, cfg)
    (OUT_DIR / "model_readiness.json").write_text(json.dumps(readiness, indent=2, default=str), encoding="utf-8")

    logger.info("MODEL_READY = %s (%s)", readiness["model_ready"], readiness["primary_reason"])

    return {
        "tables": {k: (v.shape if hasattr(v, "shape") else None) for k, v in tables.items()},
        "validation_issues": len(issues), "validation_errors": len(errors),
        "data_quality_report": dq_report, "eda_report": eda_report,
        "feature_availability_matrix": feature_matrix, "model_readiness": readiness,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true",
                         help="Re-download raw sources before ingesting (default: reuse data/raw/real/)")
    args = parser.parse_args()
    main(skip_download=not args.download)
