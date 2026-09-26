"""Stage 11B §13: NWS (National Weather Service, api.weather.gov)
weather adapter -- verified in Stage 11A/11B: no API key required (a
descriptive User-Agent header is used instead, per NWS's own docs), and
`https://api.weather.gov/stations/{id}/observations` returns real
recent-history observations covering precipitation/temperature/visibility
at roughly 5-minute (METAR) resolution. No credential of any kind is
read from anywhere but the environment (there is none to read here --
NWS genuinely requires no key).
"""
from __future__ import annotations

import logging

import pandas as pd
import requests

from src.ingestion.common.contracts import DATASET_TYPE_REAL
from src.ingestion.common.provenance import NWS_LICENSE_REFERENCE, ProvenanceRecord, build_provenance

logger = logging.getLogger("routewise.ingestion.weather.nws")

USER_AGENT = "RouteWise-MLOps-Project/1.0 (academic MLOps project; see docs/stage11a-source-license-verification.md)"
BASE_URL = "https://api.weather.gov"


def fetch_station_observations(station_id: str, start_iso: str, end_iso: str, timeout: int = 30) -> dict:
    url = f"{BASE_URL}/stations/{station_id}/observations"
    response = requests.get(
        url, params={"start": start_iso, "end": end_iso},
        headers={"User-Agent": USER_AGENT}, timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _extract_value(prop: dict | None) -> float | None:
    if prop is None:
        return None
    value = prop.get("value")
    return float(value) if value is not None else None


def observations_to_dataframe(geojson: dict) -> pd.DataFrame:
    """Converts the raw NWS GeoJSON response into a flat table. Any field
    the API itself reports as null (unitCode present, value null -- a
    real, common METAR gap, not a parsing failure) is recorded as NaN,
    never fabricated or forward-filled here."""
    rows = []
    for feature in geojson.get("features", []):
        p = feature["properties"]
        visibility_m = _extract_value(p.get("visibility"))
        rows.append({
            "timestamp": p["timestamp"],
            "temperature_c": _extract_value(p.get("temperature")),
            "precipitation_mm": _extract_value(p.get("precipitationLastHour")),
            "visibility_km": visibility_m / 1000.0 if visibility_m is not None else None,
        })
    return pd.DataFrame(rows)


def save_provenance(station_id: str, start_iso: str, end_iso: str, dest_marker_path) -> ProvenanceRecord:
    """NWS responses are fetched live, not saved as a single downloadable
    file the way GTFS/LAMP are -- this records provenance for a fetch
    window against a marker file (the normalized weather Parquet itself)
    rather than a raw-bytes checksum of a non-existent single download."""
    from pathlib import Path

    return build_provenance(
        provider="NWS (National Weather Service)",
        source_url=f"{BASE_URL}/stations/{station_id}/observations",
        downloaded_path=Path(dest_marker_path),
        license_reference=NWS_LICENSE_REFERENCE,
        dataset_type=DATASET_TYPE_REAL,
        geographic_coverage=f"station {station_id} (Boston Logan International Airport)",
        temporal_coverage=f"{start_iso}..{end_iso}",
        notes="NWS station observations -- ~5-minute METAR resolution; NOT a deep multi-year "
              "historical archive (see docs/stage11a-source-license-verification.md Section 6 "
              "for the recommended NOAA NCEI ISD source for that use case, not implemented here).",
    )
