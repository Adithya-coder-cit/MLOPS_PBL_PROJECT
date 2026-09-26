"""Stage 11B §1/§3: download the official MBTA static GTFS feed and
record its provenance. Never guesses/hardcodes an alternate URL --
configs/real_data.yaml `sources.gtfs_static.url` is the single source of
truth, pointing at the same CDN URL verified in Stage 11A/11B
(https://cdn.mbta.com/MBTA_GTFS.zip).
"""
from __future__ import annotations

import logging

import requests

from src.ingestion.common.contracts import DATASET_TYPE_REAL
from src.ingestion.common.provenance import MBTA_LICENSE_REFERENCE, ProvenanceRecord, build_provenance

logger = logging.getLogger("routewise.ingestion.gtfs.download")

USER_AGENT = "RouteWise-MLOps-Project/1.0 (academic MLOps project; see docs/stage11a-source-license-verification.md)"


def download_gtfs_feed(url: str, dest_path, timeout: int = 60) -> ProvenanceRecord:
    """Downloads the GTFS ZIP to `dest_path` and returns its provenance
    record. Does not extract -- src.ingestion.gtfs.parser reads the ZIP
    directly."""
    from pathlib import Path

    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading GTFS feed from %s", url)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    dest_path.write_bytes(response.content)
    logger.info("Wrote %d bytes to %s", len(response.content), dest_path)

    return build_provenance(
        provider="MBTA",
        source_url=url,
        downloaded_path=dest_path,
        license_reference=MBTA_LICENSE_REFERENCE,
        dataset_type=DATASET_TYPE_REAL,
        geographic_coverage="Greater Boston metropolitan area (MBTA service area) + Cape Cod RTA (CapeFLYER)",
        temporal_coverage="current schedule validity period (feed_info.txt feed_start_date..feed_end_date)",
        notes="Static GTFS -- updated by MBTA several times per month per official developer docs; "
              "this snapshot represents one point-in-time download, pinned via DVC.",
    )
