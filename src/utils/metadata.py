"""Dataset metadata that must travel with the processed feature dataset:
DVC content hashes of the raw data actually used, the generation seed,
a hash of the generation config (to detect drift), row counts, and the
raw/feature schema versions.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import yaml


def file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def dvc_out_hash(dvc_file: Path) -> str | None:
    """Read the content hash DVC recorded for a `dvc add`-tracked path,
    from its .dvc pointer file. Shared by dataset and model-training
    lineage capture (training/reproducibility.py) so both read the exact
    same pointer files the same way.
    """
    if not dvc_file.exists():
        return None
    spec = yaml.safe_load(dvc_file.read_text(encoding="utf-8"))
    outs = spec.get("outs", [])
    return outs[0]["md5"] if outs else None


# Backwards-compatible private aliases (kept in case anything imports the
# old underscored names directly).
_file_hash = file_hash
_dvc_out_hash = dvc_out_hash


def build_dataset_metadata(
    raw_dir: Path,
    synthetic_config_path: Path,
    raw_schema_version: str,
    feature_schema_version: str,
    row_counts: dict,
    split_boundaries: dict,
) -> dict:
    cfg = yaml.safe_load(synthetic_config_path.read_text(encoding="utf-8"))
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "generation_seed": cfg.get("seed"),
        "dataset_version": cfg.get("dataset_version"),
        "synthetic_config_hash": file_hash(synthetic_config_path),
        "dvc_raw_hashes": {
            "gtfs": dvc_out_hash(raw_dir / "gtfs.dvc"),
            "operational": dvc_out_hash(raw_dir / "operational.dvc"),
            "weather": dvc_out_hash(raw_dir / "weather.dvc"),
        },
        "raw_schema_version": raw_schema_version,
        "feature_schema_version": feature_schema_version,
        "row_counts": row_counts,
        "split_boundaries": split_boundaries,
    }


def write_metadata(metadata: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
