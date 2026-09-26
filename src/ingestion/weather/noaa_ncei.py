"""Stage 11B §13: NOAA NCEI (Integrated Surface Dataset) adapter --
the recommended source for a DEEP multi-year historical weather backfill
(Stage 11A Section 6), complementing src.ingestion.weather.nws (which
only covers a recent rolling window). Requires a free CDO Web Services
token, obtained by email registration at
https://www.ncdc.noaa.gov/cdo-web/token -- read from the environment
only (NOAA_CDO_TOKEN), never hardcoded, and NOT obtained or stored
during Stage 11B (per the brief's "do not commit credentials"
instruction) -- this module is provided so the adapter boundary exists
and is testable, but was not executed against a real token in this
stage. See docs/stage11a-source-license-verification.md Section 6.
"""
from __future__ import annotations

import logging
import os

import pandas as pd
import requests

logger = logging.getLogger("routewise.ingestion.weather.noaa_ncei")

BASE_URL = "https://www.ncei.noaa.gov/cdo-web/api/v2"


class MissingTokenError(Exception):
    """Raised when NOAA_CDO_TOKEN is not set -- never falls back to a
    hardcoded or default token."""


def _token() -> str:
    token = os.environ.get("NOAA_CDO_TOKEN")
    if not token:
        raise MissingTokenError(
            "NOAA_CDO_TOKEN is not set. Obtain a free token at "
            "https://www.ncdc.noaa.gov/cdo-web/token and set it as an environment variable "
            "-- never hardcode it in source or commit it to the repository."
        )
    return token


def fetch_daily_summaries(station_id: str, start_date: str, end_date: str, timeout: int = 30) -> dict:
    """station_id: an NCEI GHCND/ISD station identifier, e.g.
    'GHCND:USW00014739' for Boston Logan International Airport.
    Returns the raw CDO API JSON response. Reminder (Stage 11A): CDO's
    documented dataset here is DAILY summaries -- the hourly-resolution
    product (Integrated Surface Dataset / Local Climatological Data) is
    accessed via NCEI's bulk data-access services, not this token-gated
    REST API, and is not implemented in this module.
    """
    response = requests.get(
        f"{BASE_URL}/data",
        params={"datasetid": "GHCND", "stationid": station_id, "startdate": start_date,
                "enddate": end_date, "units": "metric", "limit": 1000},
        headers={"token": _token()}, timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def daily_summaries_to_dataframe(raw: dict) -> pd.DataFrame:
    results = raw.get("results", [])
    if not results:
        return pd.DataFrame(columns=["timestamp", "datatype", "value"])
    df = pd.DataFrame(results)
    return df.rename(columns={"date": "timestamp", "datatype": "datatype"})[["timestamp", "datatype", "value"]]
