"""Capture everything needed to reproduce a training run: code version
(git SHA), data version (Stage 3's dataset_metadata.json, DVC hashes),
config versions (params.yaml, configs/synthetic_data.yaml hashes),
environment (Python + key dependency versions), and the run's own seed.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


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
    }
