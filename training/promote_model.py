"""Explicit, human-triggered promotion of a model version to "production".

This is deliberately NOT called by training.train or
training.mlflow_tracking — nothing in this codebase promotes a model to
production automatically. Promotion requires running this script by hand,
and even then only succeeds if the version has cleared the promotion gate
(lifecycle_stage == "Validated"). Stage 10's training/retrain.py also
calls this function, but ONLY when explicitly run with
--promotion-mode auto AND the gate actually passed — never as a default,
and never for a model that hasn't cleared real evaluation criteria.

Run: python -m training.promote_model --model-name RouteWise-Disruption-Model --version 1 --confirm
"""
from __future__ import annotations

import argparse
import logging

import mlflow
from mlflow.tracking import MlflowClient

from training.mlflow_tracking import set_lifecycle_stage

logger = logging.getLogger("routewise.training.promote_model")


class PromotionRefused(Exception):
    pass


def promote(model_name: str, version: str, tracking_uri: str, confirm: bool) -> None:
    if not confirm:
        raise PromotionRefused("Refusing to promote without --confirm (this is a deliberate safety check).")

    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()
    mv = client.get_model_version(model_name, version)
    stage = (mv.tags or {}).get("lifecycle_stage")

    if stage != "Validated":
        raise PromotionRefused(
            f"Model '{model_name}' v{version} has lifecycle_stage='{stage}', not 'Validated'. "
            "It must pass the promotion gate (training/mlflow_tracking.py) before it can be promoted."
        )

    client.set_registered_model_alias(model_name, "production", version)
    set_lifecycle_stage(client, model_name, version, "Production")
    logger.info("Promoted %s v%s to production.", model_name, version)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tracking-uri", default="./mlruns")
    parser.add_argument("--confirm", action="store_true", help="Required to actually perform the promotion.")
    args = parser.parse_args()
    promote(args.model_name, args.version, args.tracking_uri, args.confirm)
