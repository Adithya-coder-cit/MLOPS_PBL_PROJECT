"""Reference/current dataset definitions for Stage 9 monitoring.

Reference = data/processed/train.parquet by default (params.yaml
monitoring.reference.split) — the chronologically EARLIEST processed
split, i.e. the distribution the currently configured model actually
trained on. Current = data/processed/test.parquet by default
(monitoring.current.split) — the chronologically LATEST split, standing
in for a "new" batch since this project has no live production traffic
yet. Both are read straight from the existing DVC-versioned artifacts —
nothing here re-derives or re-engineers a single feature.

Reference lineage is captured ONCE into reference_metadata.json and never
silently overwritten: a later run whose dataset version, DVC hash, or
feature-manifest version no longer matches what was recorded raises
ReferenceChangedError unless the caller explicitly passes force=True.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd

from src.utils.metadata import dvc_out_hash, file_hash

PROCESSED_DIR = Path("data/processed")
MONITORING_DIR = Path("data/interim/monitoring")
REFERENCE_METADATA_PATH = MONITORING_DIR / "reference_metadata.json"

SPLIT_FILES = {"train": "train.parquet", "val": "val.parquet", "test": "test.parquet"}

_REPO_ROOT = Path(__file__).resolve().parents[2]


class ReferenceChangedError(Exception):
    """Raised when the reference dataset's recorded lineage no longer
    matches what a new run observes, and the caller did not explicitly
    ask to re-establish it — monitoring must never silently compare
    against a different reference than the one it reports (Stage 9 §4)."""


def _git_commit_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, text=True).strip()
    except Exception:
        return None


def load_split(split: str, processed_dir: Path = PROCESSED_DIR) -> pd.DataFrame:
    if split not in SPLIT_FILES:
        raise ValueError(f"Unknown split '{split}', expected one of {list(SPLIT_FILES)}")
    return pd.read_parquet(processed_dir / SPLIT_FILES[split])


def load_dataset_metadata(processed_dir: Path = PROCESSED_DIR) -> dict:
    return json.loads((processed_dir / "dataset_metadata.json").read_text(encoding="utf-8"))


def load_feature_manifest(processed_dir: Path = PROCESSED_DIR) -> dict:
    return json.loads((processed_dir / "feature_manifest.json").read_text(encoding="utf-8"))


def split_period(dataset_metadata: dict, split: str) -> dict:
    """Chronological [start, end] this split covers, read from Stage 3's
    own split_boundaries — never a hardcoded date (Stage 9 §6)."""
    b = dataset_metadata["split_boundaries"]
    if split == "train":
        return {"start": b["min_date"], "end": b["train_end"]}
    if split == "val":
        return {"start": b["train_end"], "end": b["val_end"]}
    if split == "test":
        return {"start": b["val_end"], "end": b["max_date"]}
    raise ValueError(f"Unknown split '{split}'")


def build_reference_metadata(
    reference_split: str,
    model_name: str | None,
    model_version: str | None,
    model_git_sha: str | None,
    processed_dir: Path = PROCESSED_DIR,
) -> dict:
    dataset_metadata = load_dataset_metadata(processed_dir)
    feature_manifest = load_feature_manifest(processed_dir)
    return {
        "reference_split": reference_split,
        "dataset_version": dataset_metadata["dataset_version"],
        "dvc_hash": dvc_out_hash(processed_dir / f"{SPLIT_FILES[reference_split]}.dvc"),
        "feature_manifest_schema_version": feature_manifest["schema_version"],
        "feature_manifest_hash": file_hash(processed_dir / "feature_manifest.json"),
        "model_name": model_name,
        "model_version": model_version,
        "model_git_sha": model_git_sha,
        "reference_period": split_period(dataset_metadata, reference_split),
        "established_at_git_sha": _git_commit_sha(),
    }


_COMPARABLE_KEYS = ["reference_split", "dataset_version", "dvc_hash", "feature_manifest_schema_version"]


def establish_or_verify_reference(
    reference_split: str,
    model_name: str | None,
    model_version: str | None,
    model_git_sha: str | None,
    processed_dir: Path = PROCESSED_DIR,
    force: bool = False,
) -> dict:
    MONITORING_DIR.mkdir(parents=True, exist_ok=True)
    new_metadata = build_reference_metadata(reference_split, model_name, model_version, model_git_sha, processed_dir)

    if REFERENCE_METADATA_PATH.exists() and not force:
        existing = json.loads(REFERENCE_METADATA_PATH.read_text(encoding="utf-8"))
        existing_comparable = {k: existing.get(k) for k in _COMPARABLE_KEYS}
        new_comparable = {k: new_metadata.get(k) for k in _COMPARABLE_KEYS}
        if existing_comparable != new_comparable:
            raise ReferenceChangedError(
                "Reference dataset lineage changed since it was established "
                f"(existing={existing_comparable}, new={new_comparable}). "
                "Pass force=True to intentionally re-establish the reference."
            )
        return existing

    REFERENCE_METADATA_PATH.write_text(json.dumps(new_metadata, indent=2), encoding="utf-8")
    return new_metadata
