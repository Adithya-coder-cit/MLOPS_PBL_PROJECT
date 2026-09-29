"""Stage 11D: NOAA GHCNh (Global Historical Climatology Network hourly)
adapter -- https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly

Verified this stage by direct download, not from documentation claims
alone:

- Bulk access is a per-station-per-year PSV (or parquet) file, NO API key
  required:
  https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/{year}/psv/GHCNh_{station_id}_{year}.psv
- Station used: USW00014739 (Boston Logan International Airport,
  42.3606 N / -71.0097 W) -- the same physical station as the Stage 11B/C
  NWS adapter's KBOS, so both sources describe the same location.
- The full 2026 file, once fully downloaded, is genuinely current -- it
  reaches into October 2026, comfortably covering the real MBTA training
  window established in Stage 11C (2026-08-01 .. 2026-09-29). An initial
  quick `curl --max-time` probe during this stage's research appeared to
  show the file stopping at 2026-02-26, which looked like a multi-month
  publication lag; that turned out to be an artifact of an incomplete
  download (the probe's time budget cut the transfer short partway
  through a 30+ MB file, and curl did not treat the truncation as an
  error) -- NOT a real property of the source. The actual coverage/join
  results are in data/interim/real/weather_coverage_report.json, measured
  from a full, complete download via this module's own
  fetch_station_year (which does not impose an artificial time budget).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests

from src.ingestion.common.contracts import DATASET_TYPE_REAL
from src.ingestion.common.provenance import GHCNH_LICENSE_REFERENCE, ProvenanceRecord, build_provenance

logger = logging.getLogger("routewise.ingestion.weather.ghcnh")

BASE_URL = "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year"
USER_AGENT = "RouteWise-MLOps-Project/1.0 (academic MLOps project; see docs/stage11d-weather-integration.md)"

# The subset of GHCNh's ~50 raw columns this adapter actually reads --
# GHCNh publishes many more (sky cover, present-weather codes, snow depth,
# etc.) that this project's canonical weather contract has no use for and
# does not attempt to preserve.
RAW_COLUMNS = [
    "STATION", "Station_name", "DATE", "LATITUDE", "LONGITUDE",
    "temperature", "precipitation", "wind_speed", "visibility",
    "station_level_pressure", "sea_level_pressure",
]


def station_year_url(station_id: str, year: int) -> str:
    return f"{BASE_URL}/{year}/psv/GHCNh_{station_id}_{year}.psv"


def fetch_station_year(station_id: str, year: int, dest_path: Path, timeout: int = 60) -> Path:
    """Downloads one station-year PSV file to `dest_path`, raw and
    unmodified -- no parsing, no filtering. Idempotent: if `dest_path`
    already exists this does NOT re-download (mirrors the project's
    existing --download-flag convention for GTFS/LAMP raw sources)."""
    if dest_path.exists():
        logger.info("GHCNh %s %d already downloaded at %s -- skipping fetch", station_id, year, dest_path)
        return dest_path
    url = station_year_url(station_id, year)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(response.content)
    logger.info("Downloaded GHCNh %s %d (%d bytes) to %s", station_id, year, len(response.content), dest_path)
    return dest_path


def load_station_year_psv(path: Path) -> pd.DataFrame:
    """Reads one raw station-year PSV file, keeping only RAW_COLUMNS --
    every value the source itself left blank stays blank (empty string ->
    NaN via pandas' default na handling), never fabricated or interpolated
    here."""
    df = pd.read_csv(path, sep="|", usecols=lambda c: c in RAW_COLUMNS, dtype=str, na_values=[""])
    for col in ["LATITUDE", "LONGITUDE", "temperature", "precipitation", "wind_speed", "visibility",
                "station_level_pressure", "sea_level_pressure"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_station_years(paths: list[Path]) -> pd.DataFrame:
    frames = [load_station_year_psv(p) for p in paths if p.exists()]
    if not frames:
        return pd.DataFrame(columns=RAW_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def save_provenance(station_id: str, years: list[int], dest_dir: Path) -> ProvenanceRecord:
    downloaded_files = sorted(dest_dir.glob(f"GHCNh_{station_id}_*.psv"))
    marker = downloaded_files[0] if downloaded_files else dest_dir
    return build_provenance(
        provider="NOAA NCEI (Global Historical Climatology Network hourly, GHCNh v1)",
        source_url=station_year_url(station_id, years[0]) if years else BASE_URL,
        downloaded_path=marker,
        license_reference=GHCNH_LICENSE_REFERENCE,
        dataset_type=DATASET_TYPE_REAL,
        geographic_coverage=f"station {station_id} (Boston Logan International Airport)",
        temporal_coverage=f"requested years {years}",
        notes="Bulk per-station-per-year PSV download, no API key. Confirmed current through "
              "early October 2026 as of this stage's retrieval -- covers the real MBTA training "
              "window (2026-08-01..2026-09-29). See "
              "data/interim/real/weather_coverage_report.json for the measured join coverage.",
    )
