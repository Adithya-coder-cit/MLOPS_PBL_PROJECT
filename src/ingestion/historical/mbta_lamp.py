"""Stage 11B §1/§10: loaders for the official MBTA LAMP historical
performance exports (verified field-by-field against the official Data
Dictionary in Stage 11A -- https://github.com/mbta/lamp/blob/main/Data_Dictionary.md).

Two real, distinct datasets, each with its own schema (not unified here --
src.ingestion.historical.normalize is where they converge onto the
canonical contract):

- Subway/rapid-transit performance: one Parquet file per service_date,
  listed in a public index CSV.
- Bus performance: a single rolling-window Parquet
  ("LAMP_RECENT_Bus_Events.parquet" -- verified as a 7-day window at
  Stage 11B time, NOT the full multi-GB historical archive
  "LAMP_ALL_Bus_Events.parquet", which was not downloaded in this stage
  -- see the Stage 11B report's documented scope limitation).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests

from src.ingestion.common.contracts import DATASET_TYPE_REAL
from src.ingestion.common.provenance import MBTA_LICENSE_REFERENCE, ProvenanceRecord, build_provenance
from src.ingestion.gtfs.download import USER_AGENT

logger = logging.getLogger("routewise.ingestion.historical.mbta_lamp")


def fetch_subway_index(index_url: str, timeout: int = 30) -> pd.DataFrame:
    """The public CSV listing every available subway-performance
    service_date and its Parquet URL."""
    response = requests.get(index_url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    from io import StringIO

    return pd.read_csv(StringIO(response.text))


def download_subway_day(file_url: str, dest_path: Path, timeout: int = 60) -> ProvenanceRecord:
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(file_url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    dest_path.write_bytes(response.content)
    return build_provenance(
        provider="MBTA LAMP", source_url=file_url, downloaded_path=dest_path,
        license_reference=MBTA_LICENSE_REFERENCE, dataset_type=DATASET_TYPE_REAL,
        geographic_coverage="MBTA rapid transit (subway + light rail)",
        temporal_coverage="single service_date",
    )


def download_bus_events(url: str, dest_path: Path, timeout: int = 300) -> ProvenanceRecord:
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading bus events from %s (this file is tens to hundreds of MB)", url)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    dest_path.write_bytes(response.content)
    return build_provenance(
        provider="MBTA LAMP", source_url=url, downloaded_path=dest_path,
        license_reference=MBTA_LICENSE_REFERENCE, dataset_type=DATASET_TYPE_REAL,
        geographic_coverage="MBTA bus network",
        temporal_coverage="rolling recent window (verified 7 days at Stage 11B time; "
                           "re-verify at ingestion time, MBTA does not document a fixed retention period)",
        notes="LAMP_RECENT_Bus_Events.parquet -- the bounded rolling-window export, not the full "
              "multi-GB LAMP_ALL_Bus_Events.parquet archive (not ingested in this stage).",
    )


def load_subway_performance(parquet_paths: list[Path]) -> pd.DataFrame:
    frames = [pd.read_parquet(p) for p in parquet_paths]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_bus_events(parquet_path: Path) -> pd.DataFrame:
    return pd.read_parquet(parquet_path)
