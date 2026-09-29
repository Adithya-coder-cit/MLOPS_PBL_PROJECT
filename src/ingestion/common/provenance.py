"""Stage 11B §3: machine-readable provenance for every real-data source
RouteWise ingests. One ProvenanceRecord per downloaded file/feed —
written alongside the raw data (never containing credentials, only a
reference to which license governs the source).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.utils.metadata import file_hash


@dataclass
class ProvenanceRecord:
    provider: str
    source_url: str
    retrieved_at: str
    source_file_or_feed: str
    checksum_sha256_16: str | None
    license_reference: str
    dataset_type: str  # "REAL" | "DEMO"
    geographic_coverage: str
    temporal_coverage: str
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProvenanceLog:
    records: list[ProvenanceRecord] = field(default_factory=list)

    def add(self, record: ProvenanceRecord) -> None:
        self.records.append(record)

    def to_dict(self) -> dict:
        return {"records": [r.to_dict() for r in self.records]}

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


MBTA_LICENSE_REFERENCE = (
    "MassDOT Developers License Agreement "
    "(https://www.mass.gov/files/documents/2017/10/27/develop_license_agree_0.pdf) "
    "-- see docs/stage11a-source-license-verification.md for the full clause-by-clause "
    "reading. Attribution to MassDOT/MBTA is required by this license (Sec 4.1)."
)

NWS_LICENSE_REFERENCE = (
    "U.S. National Weather Service API (api.weather.gov) -- \"open data, free to use "
    "for any purpose\" per the official API documentation; no separate agreement."
)

GHCNH_LICENSE_REFERENCE = (
    "NOAA Global Historical Climatology Network hourly (GHCNh), Version 1 -- "
    "https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly -- "
    "NOAA data, information, and products are not subject to copyright protection in the "
    "United States and are provided free of charge; no separate license agreement or API "
    "token is required for bulk PSV/parquet download."
)


def build_provenance(
    provider: str,
    source_url: str,
    downloaded_path: Path,
    license_reference: str,
    dataset_type: str,
    geographic_coverage: str,
    temporal_coverage: str,
    notes: str = "",
) -> ProvenanceRecord:
    return ProvenanceRecord(
        provider=provider,
        source_url=source_url,
        retrieved_at=datetime.now(UTC).isoformat(timespec="seconds"),
        source_file_or_feed=downloaded_path.name,
        checksum_sha256_16=file_hash(downloaded_path),
        license_reference=license_reference,
        dataset_type=dataset_type,
        geographic_coverage=geographic_coverage,
        temporal_coverage=temporal_coverage,
        notes=notes,
    )
