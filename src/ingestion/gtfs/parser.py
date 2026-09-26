"""Stage 11B §5: parse the official GTFS static ZIP. Reads required files
unconditionally and optional files ONLY where present -- never fails
merely because an optional GTFS file is absent (per the brief).
"""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import pandas as pd

logger = logging.getLogger("routewise.ingestion.gtfs.parser")

REQUIRED_FILES = ["stops.txt", "routes.txt", "trips.txt", "stop_times.txt", "calendar.txt", "calendar_dates.txt"]
OPTIONAL_FILES = ["transfers.txt", "shapes.txt", "fare_attributes.txt", "fare_rules.txt",
                   "fare_products.txt", "fare_leg_rules.txt", "route_patterns.txt", "agency.txt", "feed_info.txt"]

# GTFS allows a feed to define service via calendar.txt, calendar_dates.txt,
# or both -- calendar.txt itself is technically conditionally required, not
# unconditionally required. We still read it eagerly (most feeds have it,
# including MBTA's) but do not fail if it's genuinely absent, only if BOTH
# calendar files are missing (see validate_calendar_presence below).
_CONDITIONALLY_REQUIRED = {"calendar.txt", "calendar_dates.txt"}


def parse_gtfs_zip(zip_path: Path) -> dict[str, pd.DataFrame]:
    zip_path = Path(zip_path)
    tables: dict[str, pd.DataFrame] = {}

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())

        for filename in REQUIRED_FILES:
            key = filename.removesuffix(".txt")
            if filename in names:
                with zf.open(filename) as f:
                    tables[key] = pd.read_csv(f, dtype=str, low_memory=False)
            elif filename in _CONDITIONALLY_REQUIRED:
                logger.info("%s not present in feed (conditionally required -- OK if the other "
                            "calendar file is present)", filename)
            else:
                raise FileNotFoundError(f"Required GTFS file '{filename}' missing from {zip_path}")

        if "calendar" not in tables and "calendar_dates" not in tables:
            raise FileNotFoundError(
                f"Neither calendar.txt nor calendar_dates.txt present in {zip_path} -- "
                "GTFS requires at least one to define service."
            )

        for filename in OPTIONAL_FILES:
            key = filename.removesuffix(".txt")
            if filename in names:
                with zf.open(filename) as f:
                    tables[key] = pd.read_csv(f, dtype=str, low_memory=False)
            else:
                logger.info("Optional GTFS file '%s' not present -- skipping, not failing.", filename)

    logger.info("Parsed GTFS feed: %s", {k: len(v) for k, v in tables.items()})
    return tables
