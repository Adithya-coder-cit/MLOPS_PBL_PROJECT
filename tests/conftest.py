"""Shared fixtures for the routing/decision-engine tests. The real
routing graph is built once per test session (it involves real model
inference) and reused — building it fresh per test would be slow and
wouldn't test anything different.
"""
from pathlib import Path

import pytest
import yaml

MODEL_ARTIFACTS_EXIST = Path("data/interim/joined_training_events.parquet").exists()

ROUTING_STACK_AVAILABLE = MODEL_ARTIFACTS_EXIST


def _mlflow_candidate_available() -> bool:
    try:
        import mlflow
        from mlflow.tracking import MlflowClient
    except Exception:
        return False
    try:
        mlflow.set_tracking_uri("./mlruns")
        client = MlflowClient()
        versions = client.search_model_versions("name='RouteWise-Disruption-Model'")
        return len(versions) > 0
    except Exception:
        return False


# Public alias — other test modules import this rather than duplicating
# the registry check. Data existing (MODEL_ARTIFACTS_EXIST) does NOT
# imply a model is registered (e.g. CI's ci.yml generates data but never
# trains/registers a model — see README "CI/CD workflows"), so any test
# that needs an actual registered candidate must check BOTH.
mlflow_candidate_available = _mlflow_candidate_available

requires_routing_stack = pytest.mark.skipif(
    not MODEL_ARTIFACTS_EXIST, reason="Stage 3 interim feature table not generated yet"
)

requires_registered_model = pytest.mark.skipif(
    not _mlflow_candidate_available(), reason="No registered MLflow candidate model available in ./mlruns"
)


@pytest.fixture(scope="session")
def params_config():
    return yaml.safe_load(Path("params.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def synthetic_config():
    return yaml.safe_load(Path("configs/synthetic_data.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def prediction_source():
    if not _mlflow_candidate_available():
        pytest.skip("No registered candidate model available in ./mlruns")
    from src.routing.prediction_source import get_prediction_source
    return get_prediction_source("candidate", candidate_version="4")


@pytest.fixture(scope="session")
def preprocessor():
    import joblib
    path = Path("data/processed/preprocessor.joblib")
    if not path.exists():
        pytest.skip("preprocessor.joblib not available")
    return joblib.load(path)


@pytest.fixture(scope="session")
def routing_graph(params_config, synthetic_config, prediction_source, preprocessor):
    from src.routing.graph_builder import QueryContext, build_routing_graph
    qctx = QueryContext.from_config(params_config)
    graph, lineage = build_routing_graph(prediction_source, qctx, synthetic_config, preprocessor=preprocessor)
    return graph, lineage
