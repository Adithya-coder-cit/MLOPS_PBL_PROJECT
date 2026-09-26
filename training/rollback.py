"""Stage 10 §11: rollback capability. Re-points the "production" alias to
a previously VALIDATED (or already-Production) model version. Never
deletes any version — MLflow's registry keeps full, auditable history
regardless of alias changes. This is deliberately a SEPARATE, explicit,
human/CI-triggered action (mirrors training/promote_model.py's own
"nothing here is automatic" philosophy) — never called implicitly by
retrain.py or the monitoring pipeline.

Run: python -m training.rollback --model-name RouteWise-Disruption-Model --to-version 2 --confirm
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime

import mlflow
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from training.mlflow_tracking import set_lifecycle_stage

logger = logging.getLogger("routewise.training.rollback")

ROLLBACK_ELIGIBLE_STAGES = ("Validated", "Production")


class RollbackRefused(Exception):
    pass


def _verify_target_version(client: MlflowClient, model_name: str, target_version: str) -> dict:
    try:
        mv = client.get_model_version(model_name, target_version)
    except MlflowException as e:
        raise RollbackRefused(f"Model '{model_name}' version {target_version} does not exist: {e}") from e

    stage = (mv.tags or {}).get("lifecycle_stage")
    if stage not in ROLLBACK_ELIGIBLE_STAGES:
        raise RollbackRefused(
            f"Model '{model_name}' v{target_version} has lifecycle_stage='{stage}' — only versions that were "
            f"{ROLLBACK_ELIGIBLE_STAGES} are eligible for rollback (never an untested Candidate)."
        )

    run = client.get_run(mv.run_id)
    if run.data.metrics.get("signature_roundtrip_validated") != 1.0:
        raise RollbackRefused(
            f"Model '{model_name}' v{target_version}'s run has no verified 'signature_roundtrip_validated' metric "
            "— its model signature was never proven to round-trip correctly at registration time."
        )

    required_tags = {"lifecycle_stage", "model_flavor"}
    missing_tags = required_tags - set((mv.tags or {}).keys())
    if missing_tags:
        raise RollbackRefused(f"Model '{model_name}' v{target_version} is missing required metadata tag(s): "
                               f"{missing_tags}")

    return {
        "model_version": mv.version, "lifecycle_stage": stage, "model_flavor": mv.tags.get("model_flavor"),
        "run_id": mv.run_id,
    }


def _current_production_version(client: MlflowClient, model_name: str) -> str | None:
    try:
        return client.get_model_version_by_alias(model_name, "production").version
    except MlflowException:
        return None


def rollback(
    model_name: str, target_version: str, tracking_uri: str = "./mlruns",
    confirm: bool = False, dry_run: bool = False,
) -> dict:
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()

    target_info = _verify_target_version(client, model_name, target_version)
    previous_production_version = _current_production_version(client, model_name)

    plan = {
        "model_name": model_name,
        "from_version": previous_production_version,
        "to_version": target_version,
        "was_real_production_rollback": previous_production_version is not None,
        "target_metadata": target_info,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }

    if dry_run or not confirm:
        plan["executed"] = False
        plan["reason"] = "dry_run" if dry_run else "confirm not set"
        logger.info("Rollback plan (not executed): %s -> %s (%s)", plan["from_version"], plan["to_version"],
                    plan["reason"])
        return plan

    client.set_registered_model_alias(model_name, "production", target_version)
    set_lifecycle_stage(client, model_name, target_version, "Production")

    # Record the rollback event as its own lightweight, auditable MLflow
    # run — never overwrites or deletes the target/previous versions'
    # own history.
    mlflow.set_experiment(f"{model_name}-rollback-events")
    with mlflow.start_run(run_name=f"rollback_to_v{target_version}"):
        mlflow.set_tags({
            "event": "rollback",
            "model_name": model_name,
            "from_version": str(previous_production_version),
            "to_version": str(target_version),
            "was_real_production_rollback": str(previous_production_version is not None),
            "rollback_timestamp": plan["timestamp"],
        })

    plan["executed"] = True
    logger.info("Rollback executed: %s v%s is now 'production' (was v%s).",
                model_name, target_version, previous_production_version)
    return plan


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--to-version", required=True)
    parser.add_argument("--tracking-uri", default="./mlruns")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm", action="store_true", help="Required to actually perform the rollback.")
    args = parser.parse_args()
    rollback(args.model_name, args.to_version, args.tracking_uri, confirm=args.confirm, dry_run=args.dry_run)
