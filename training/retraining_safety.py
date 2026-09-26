"""Stage 10 §3: pre-flight safety checks the retraining pipeline must
pass BEFORE any training happens. Reuses existing verification wherever
it already exists (training/data_loader.py's schema + temporal checks,
DVC's own `dvc status`) rather than re-implementing it. Never trains
against partially invalid data — any ERROR-level issue stops the run.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path

from training.data_loader import PROCESSED_DIR, SchemaVerificationError, load_processed_datasets

ERROR = "ERROR"
WARNING = "WARNING"

REQUIRED_CONFIG_SECTIONS = [
    "data", "features", "model", "decision_engine", "routing", "mlflow", "evaluation", "training", "monitoring",
]

REQUIRED_PROCESSED_FILES = [
    "train.parquet", "val.parquet", "test.parquet", "preprocessor.joblib",
    "feature_manifest.json", "dataset_metadata.json",
]

REQUIREMENTS_PATH = Path("requirements.txt")
# Fallback only for callers that don't pass params.yaml's
# retraining.dependency_compatibility_check list (e.g. ad hoc scripts) —
# normal callers (retrain.py) always pass the configured list.
DEFAULT_TRAINING_DEPENDENCIES = ["pandas", "numpy", "scikit-learn", "xgboost", "mlflow", "pyyaml"]


@dataclass
class SafetyIssue:
    level: str  # ERROR | WARNING
    check: str
    message: str

    def to_dict(self) -> dict:
        return {"level": self.level, "check": self.check, "message": self.message}


class SafetyCheckError(Exception):
    """Raised when one or more ERROR-level safety issues are found —
    the retraining pipeline must stop, not train on partially invalid
    data (Stage 10 §3)."""


def check_dataset_exists(processed_dir: Path) -> list[SafetyIssue]:
    missing = [f for f in REQUIRED_PROCESSED_FILES if not (processed_dir / f).exists()]
    if missing:
        return [SafetyIssue(ERROR, "dataset_exists",
                             f"Missing processed dataset file(s) in {processed_dir}: {missing}. "
                             f"Run `python -m src.features.build_dataset` first.")]
    return []


def check_dvc_state() -> list[SafetyIssue]:
    if not Path(".dvc").exists():
        return [SafetyIssue(ERROR, "dvc_state", "No .dvc/ directory found — DVC is not initialized.")]
    try:
        result = subprocess.run(["dvc", "status"], capture_output=True, text=True, timeout=60, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return [SafetyIssue(ERROR, "dvc_state", f"Could not run `dvc status`: {e}")]
    if result.returncode != 0:
        return [SafetyIssue(ERROR, "dvc_state", f"`dvc status` failed (exit {result.returncode}): {result.stderr}")]
    output = (result.stdout or "").strip()
    if output and "up to date" not in output.lower():
        return [SafetyIssue(WARNING, "dvc_state", f"DVC reports uncommitted/out-of-date artifacts: {output}")]
    return []


def check_feature_manifest_and_schema(processed_dir: Path) -> list[SafetyIssue]:
    try:
        load_processed_datasets(processed_dir)
    except SchemaVerificationError as e:
        return [SafetyIssue(ERROR, "feature_manifest_schema", str(e))]
    except FileNotFoundError as e:
        return [SafetyIssue(ERROR, "feature_manifest_schema", f"Required file missing: {e}")]
    return []


def check_config_valid(params_config: dict) -> list[SafetyIssue]:
    issues = []
    missing = [s for s in REQUIRED_CONFIG_SECTIONS if s not in params_config]
    if missing:
        issues.append(SafetyIssue(ERROR, "config_valid", f"params.yaml is missing required section(s): {missing}"))
    if "training" in params_config and "seed" not in params_config.get("training", {}):
        issues.append(SafetyIssue(ERROR, "config_valid", "params.yaml training section is missing 'seed'"))
    return issues


def _parse_pinned_versions(requirements_path: Path) -> dict[str, str]:
    pinned = {}
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        match = re.match(r"^([A-Za-z0-9_.\-\[\]]+)==([\w.\-]+)$", line)
        if match:
            name = re.sub(r"\[.*\]", "", match.group(1))  # strip extras like uvicorn[standard]
            pinned[name.lower()] = match.group(2)
    return pinned


def check_dependencies_compatible(
    dependencies: list[str] | None = None, requirements_path: Path = REQUIREMENTS_PATH,
) -> list[SafetyIssue]:
    dependencies = dependencies if dependencies is not None else DEFAULT_TRAINING_DEPENDENCIES
    if not requirements_path.exists():
        return [SafetyIssue(WARNING, "dependencies_compatible", f"{requirements_path} not found — skipping check.")]
    pinned = _parse_pinned_versions(requirements_path)
    issues = []
    for pkg in dependencies:
        pinned_version = pinned.get(pkg.lower())
        if pinned_version is None:
            continue
        try:
            actual_version = installed_version(pkg)
        except PackageNotFoundError:
            issues.append(SafetyIssue(ERROR, "dependencies_compatible", f"'{pkg}' is required but not installed."))
            continue
        if actual_version != pinned_version:
            issues.append(SafetyIssue(
                ERROR, "dependencies_compatible",
                f"'{pkg}' installed version {actual_version} != requirements.txt pin {pinned_version}.",
            ))
    return issues


def run_safety_checks(params_config: dict, processed_dir: Path = PROCESSED_DIR) -> list[SafetyIssue]:
    issues: list[SafetyIssue] = []
    issues += check_dataset_exists(processed_dir)
    if any(i.level == ERROR for i in issues):
        return issues  # can't safely run schema checks without the files present
    issues += check_dvc_state()
    issues += check_feature_manifest_and_schema(processed_dir)
    issues += check_config_valid(params_config)
    dependencies = params_config.get("retraining", {}).get("dependency_compatibility_check")
    issues += check_dependencies_compatible(dependencies)
    return issues


def raise_if_unsafe(issues: list[SafetyIssue]) -> None:
    errors = [i for i in issues if i.level == ERROR]
    if errors:
        messages = [f"[{i.check}] {i.message}" for i in errors]
        raise SafetyCheckError(
            f"{len(errors)} safety check error(s) — refusing to train on partially invalid data:\n"
            + "\n".join(messages)
        )
