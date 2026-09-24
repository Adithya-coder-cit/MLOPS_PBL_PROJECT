"""Capture everything needed to reproduce a training run: code version
(git SHA), data version (Stage 3's dataset_metadata.json, DVC hashes),
config versions (params.yaml, configs/synthetic_data.yaml hashes),
environment (Python + key dependency versions), and the run's own seed.
"""
from __future__ import annotations

import subprocess
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path

from src.utils.metadata import dvc_out_hash, file_hash

_file_hash = file_hash


def _git_commit_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], text=True
        ).strip()
    except Exception:
        return None


def _git_dirty() -> bool | None:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=Path(__file__).resolve().parents[1], text=True
        )
        return bool(out.strip())
    except Exception:
        return None


def processed_dvc_hashes(
    processed_dir: Path = Path("data/processed"), interim_dir: Path = Path("data/interim")
) -> dict:
    return {
        "interim_joined_training_events": dvc_out_hash(interim_dir / "joined_training_events.parquet.dvc"),
        "train_parquet": dvc_out_hash(processed_dir / "train.parquet.dvc"),
        "val_parquet": dvc_out_hash(processed_dir / "val.parquet.dvc"),
        "test_parquet": dvc_out_hash(processed_dir / "test.parquet.dvc"),
        "preprocessor_joblib": dvc_out_hash(processed_dir / "preprocessor.joblib.dvc"),
    }


def capture_run_metadata(dataset_metadata: dict, feature_manifest: dict, seed: int) -> dict:
    dependency_versions = {}
    for pkg in ["xgboost", "scikit-learn", "pandas", "numpy", "mlflow", "joblib"]:
        try:
            dependency_versions[pkg] = pkg_version(pkg)
        except Exception:
            dependency_versions[pkg] = None

    return {
        "git_commit_sha": _git_commit_sha(),
        "git_working_tree_dirty": _git_dirty(),
        "params_yaml_hash": _file_hash(Path("params.yaml")),
        "synthetic_data_yaml_hash": _file_hash(Path("configs/synthetic_data.yaml")),
        "python_version": sys.version.split()[0],
        "dependency_versions": dependency_versions,
        "training_seed": seed,
        "feature_manifest_schema_version": feature_manifest.get("schema_version"),
        "dataset_metadata": dataset_metadata,
        "processed_dvc_hashes": processed_dvc_hashes(),
    }
