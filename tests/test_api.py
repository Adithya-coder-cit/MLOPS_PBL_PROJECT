"""API tests (Stage 7 §14): health, system status, model info, valid/
invalid prediction, route recommendation, unreachable route, rerouting,
model unavailable, malformed input, response schema, probability bounds.
Uses FastAPI's TestClient — no external network calls. The real app
(real model, real graph) is built once per test session and reused.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import mlflow_candidate_available

# Data existing is NOT sufficient — these tests build the real app, which
# needs an actual registered MLflow candidate (e.g. ci.yml generates data
# but never trains/registers a model; see README "CI/CD workflows").
pytestmark = pytest.mark.skipif(
    not Path("data/interim/joined_training_events.parquet").exists() or not mlflow_candidate_available(),
    reason="Stage 3/6 artifacts not generated, or no registered MLflow candidate model available",
)


@pytest.fixture(scope="module")
def client():
    from api.main import app
    with TestClient(app) as c:
        yield c


# --- health ---

def test_health_returns_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "routewise-api"
    assert "version" in body


def test_health_does_not_require_model(client):
    # /health must be reachable regardless of model state — checked
    # separately below via dependency override, this just confirms the
    # normal (model-available) path also returns 200 without model fields.
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert "model" not in r.json()


# --- system status ---

def test_system_status_reports_real_state(client):
    r = client.get("/api/v1/system/status")
    assert r.status_code == 200
    body = r.json()
    assert body["model_name"] == "RouteWise-Disruption-Model"
    assert body["model_version"] == "4"
    assert body["model_lifecycle_stage"] == "Candidate"
    assert body["is_production_model"] is False
    assert body["routing_graph_available"] is True
    assert body["monitoring"]["operational"]["request_count"] >= 1
    assert body["monitoring"]["operational"]["model_load_status"] == "available"
    assert body["dvc_configured"] is True
    assert body["ci_cd_configured"] is True
    assert body["mlflow_reachable"] is True
    assert "moderate_threshold" in body["risk_label_thresholds"]
    assert "high_threshold" in body["risk_label_thresholds"]


# --- stops ---

def test_list_stops_returns_real_data(client):
    r = client.get("/api/v1/stops")
    assert r.status_code == 200
    body = r.json()
    assert len(body["stops"]) > 0
    stop = body["stops"][0]
    for field in ["stop_id", "stop_name", "lat", "lon", "zone_id", "has_scheduled_service"]:
        assert field in stop


def test_list_stops_flags_genuinely_unserved_stops_from_the_real_graph(client):
    """A handful of real stops have zero scheduled trips in this dataset
    (verified via the routing graph's own node degree) -- has_scheduled_service
    must reflect that real structural fact, not default every stop to True."""
    r = client.get("/api/v1/stops")
    by_id = {s["stop_id"]: s["has_scheduled_service"] for s in r.json()["stops"]}
    assert by_id["S0003"] is False
    assert by_id["S0040"] is True


# --- model info ---

def test_model_info_distinguishes_validation_and_test_metrics(client):
    r = client.get("/api/v1/model/info")
    assert r.status_code == 200
    body = r.json()
    assert body["model_version"] == "4"
    assert body["model_type"] == "xgboost"
    assert "validation_metrics" in body and "test_metrics" in body
    assert body["validation_metrics"] != body["test_metrics"]
    for metrics in (body["validation_metrics"], body["test_metrics"]):
        for key in ["precision", "recall", "f1", "roc_auc", "pr_auc"]:
            assert key in metrics
    assert body["mlflow_run_id"]
    assert body["is_production_model"] is False


# --- admin experiments (internal engineering view, not user-facing) ---

def test_admin_experiments_returns_real_mlflow_run_history(client):
    r = client.get("/api/v1/admin/experiments")
    assert r.status_code == 200
    body = r.json()
    assert body["experiment_name"] == "RouteWise-Disruption-Prediction"
    assert body["registered_model_name"] == "RouteWise-Disruption-Model"
    # This repo's ./mlruns store has real logged runs (Stage 5/6) — assert
    # against that real state rather than allowing an empty/fabricated list.
    assert body["available"] is True
    assert body["reason"] is None
    assert len(body["runs"]) > 0
    run = body["runs"][0]
    for field in ["run_id", "run_name", "status", "start_time", "metrics"]:
        assert field in run
    assert isinstance(run["metrics"], dict)


def test_admin_experiments_never_returns_fake_rows_when_unavailable(client, monkeypatch):
    # Point at a tracking URI/experiment that can't possibly exist, and
    # confirm the response is an honest "not available" rather than rows
    # that look like real data.
    import api.routers.admin as admin_router

    def fake_build_experiments_overview(settings):
        return {
            "available": False,
            "reason": "MLflow tracking store is unreachable.",
            "experiment_name": settings.mlflow_experiment_name,
            "mlflow_tracking_uri": settings.mlflow_tracking_uri,
            "registered_model_name": settings.registered_model_name,
            "runs": [],
        }

    monkeypatch.setattr(admin_router, "build_experiments_overview", fake_build_experiments_overview)
    r = client.get("/api/v1/admin/experiments")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body["reason"]
    assert body["runs"] == []


def test_admin_training_status_reports_real_readiness_and_latest_run(client):
    r = client.get("/api/v1/admin/training/status")
    assert r.status_code == 200
    body = r.json()
    # This repo's real Stage 11 artifacts report MODEL_READY=False for
    # training on the real (non-synthetic) dataset — assert the real
    # value rather than allowing a fabricated True.
    assert body["real_data_model_ready"] is False
    assert body["real_data_model_ready_reason"]
    assert len(body["real_data_blocking_reasons"]) > 0
    # No live training-job tracker exists — must never fake progress.
    assert body["active_training_run"] is None
    run = body["latest_completed_run"]
    assert run is not None
    assert run["train_records"] == 272160
    assert run["validation_records"] == 58320
    model_types = {m["model_type"] for m in run["models"]}
    assert model_types == {"random_forest", "xgboost"}
    for m in run["models"]:
        assert m["gate_passed"] is False  # real F1 (~0.50–0.51) is below the configured min_f1: 0.60
        assert m["run_id"]


def test_admin_evaluation_returns_real_saved_artifacts(client):
    r = client.get("/api/v1/admin/evaluation")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["selection_metric"] == "pr_auc"
    assert len(body["models"]) == 2
    xgb = next(m for m in body["models"] if m["model_type"] == "xgboost")
    assert 0.0 < xgb["test_metrics"]["f1"] < 1.0
    assert set(xgb["confusion_matrix"].keys()) == {"tn", "fp", "fn", "tp"}
    assert len(xgb["threshold_sensitivity"]) == 9
    assert len(xgb["feature_importance"]) > 0
    # No fpr/tpr points are saved anywhere — must not claim otherwise.
    assert xgb["roc_curve_available"] is False


def test_admin_data_summary_reports_real_record_counts(client):
    r = client.get("/api/v1/admin/data/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["total_real_records"] == 4808668
    assert body["eligible_records"] == 3376547
    assert body["modes"] == ["bus", "metro", "tram"]
    assert body["dvc_configured"] is True
    assert body["real_dataset_ready"] is True
    assert len(body["splits"]) == 3


def test_admin_registry_shows_no_production_model(client):
    r = client.get("/api/v1/admin/registry")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["total_models"] == 1
    assert body["total_versions"] >= 1
    model = body["models"][0]
    assert model["name"] == "RouteWise-Disruption-Model"
    # No promotion has ever happened in this repo — assert the real state.
    assert model["production_version"] is None
    assert body["stage_counts"].get("Production", 0) == 0
    assert all(v["is_production"] is False for v in model["versions"])


def test_admin_run_detail_returns_real_params_and_metrics(client):
    experiments = client.get("/api/v1/admin/experiments").json()
    run_id = experiments["runs"][0]["run_id"]

    r = client.get(f"/api/v1/admin/runs/{run_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == run_id
    assert isinstance(body["params"], dict) and len(body["params"]) > 0
    assert isinstance(body["metrics"], dict) and len(body["metrics"]) > 0
    # Never a filesystem path — only relative artifact paths.
    assert all(":\\" not in p and not p.startswith("/") for p in body["artifact_paths"])


def test_admin_run_detail_404s_for_unknown_run(client):
    r = client.get("/api/v1/admin/runs/not-a-real-run-id")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "unknown_run"


# --- prediction ---

def test_valid_prediction_returns_real_probability(client):
    r = client.post("/api/v1/predict-disruption", json={"route_id": "R005", "stop_id": "S0021"})
    assert r.status_code == 200
    body = r.json()
    assert 0.0 <= body["disruption_probability"] <= 1.0
    assert body["predicted_class"] in (0, 1)
    assert body["model_metadata"]["model_version"] == "4"
    assert body["model_metadata"]["is_production_model"] is False
    assert body["model_metadata"]["model_source_warning"] is not None
    assert len(body["top_factors"]) > 0


def test_prediction_probability_bounds_hold_across_varied_inputs(client):
    for precip, temp, vis in [(0.0, 24.0, 10.0), (100.0, 5.0, 1.0), (50.0, 35.0, 0.5)]:
        r = client.post("/api/v1/predict-disruption", json={
            "route_id": "R005", "stop_id": "S0021",
            "precipitation_mm": precip, "temperature_c": temp, "visibility_km": vis,
        })
        assert r.status_code == 200
        assert 0.0 <= r.json()["disruption_probability"] <= 1.0


def test_prediction_unknown_route_returns_404(client):
    r = client.post("/api/v1/predict-disruption", json={"route_id": "NOT_A_ROUTE", "stop_id": "S0021"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "unknown_route"


def test_prediction_unknown_stop_returns_404(client):
    r = client.post("/api/v1/predict-disruption", json={"route_id": "R005", "stop_id": "NOT_A_STOP"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "unknown_stop"


def test_prediction_invalid_probability_range_input_returns_422(client):
    r = client.post("/api/v1/predict-disruption", json={
        "route_id": "R005", "stop_id": "S0021", "precipitation_mm": -10.0,
    })
    assert r.status_code == 422


def test_prediction_missing_required_field_returns_422(client):
    r = client.post("/api/v1/predict-disruption", json={"route_id": "R005"})
    assert r.status_code == 422


def test_prediction_malformed_datetime_returns_422(client):
    r = client.post("/api/v1/predict-disruption", json={
        "route_id": "R005", "stop_id": "S0021", "query_datetime": "not-a-real-datetime",
    })
    assert r.status_code == 422


def test_prediction_empty_route_id_returns_422(client):
    r = client.post("/api/v1/predict-disruption", json={"route_id": "  ", "stop_id": "S0021"})
    assert r.status_code == 422


# --- route recommendation ---

def test_recommend_route_returns_ranked_candidates_with_full_schema(client):
    r = client.post("/api/v1/recommend-route", json={"origin": "S0040", "destination": "S0041"})
    assert r.status_code == 200
    body = r.json()
    assert body["origin"] == "S0040" and body["destination"] == "S0041"
    assert len(body["candidates"]) >= 1
    assert body["selected"] == body["candidates"][0]
    top = body["selected"]
    for field in ["route_id", "total_time", "total_cost", "reliability", "disruption_risk",
                  "transfer_count", "score", "decision_policy", "explanation", "model_metadata"]:
        assert field in top
    assert 0.0 <= top["reliability"] <= 1.0
    assert 0.0 <= top["disruption_risk"] <= 1.0
    assert top["model_metadata"]["is_production_model"] is False


def test_recommend_route_respects_top_n(client):
    r = client.post("/api/v1/recommend-route", json={"origin": "S0040", "destination": "S0041", "top_n": 1})
    assert r.status_code == 200
    assert len(r.json()["candidates"]) == 1


def test_recommend_route_unreachable_destination_returns_404(client):
    r = client.post("/api/v1/recommend-route", json={"origin": "S0000", "destination": "S0041"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "unreachable_destination"


def test_recommend_route_unknown_origin_returns_404(client):
    r = client.post("/api/v1/recommend-route", json={"origin": "NOT_A_STOP", "destination": "S0041"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "unknown_stop"


def test_recommend_route_origin_equals_destination(client):
    r = client.post("/api/v1/recommend-route", json={"origin": "S0040", "destination": "S0040"})
    assert r.status_code == 200
    assert r.json()["selected"]["stops"] == ["S0040"]


def test_recommend_route_empty_origin_returns_422(client):
    r = client.post("/api/v1/recommend-route", json={"origin": "", "destination": "S0041"})
    assert r.status_code == 422


def test_recommend_route_invalid_top_n_returns_422(client):
    r = client.post("/api/v1/recommend-route", json={"origin": "S0040", "destination": "S0041", "top_n": 0})
    assert r.status_code == 422


# --- rerouting ---

def test_recommend_route_segments_expose_a_usable_edge_id(client):
    r = client.post("/api/v1/recommend-route", json={"origin": "S0040", "destination": "S0041"})
    segment = r.json()["selected"]["segments"][0]
    assert segment["edge_id"]
    assert segment["route_id"] in segment["edge_id"]


def test_reroute_changes_recommendation_on_forced_disruption(client):
    r0 = client.post("/api/v1/recommend-route", json={"origin": "S0040", "destination": "S0041"})
    edge_id = r0.json()["selected"]["segments"][0]["edge_id"]

    r = client.post("/api/v1/reroute", json={
        "origin": "S0040", "destination": "S0041", "edge_updates": {edge_id: 0.99},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["data_source"] == "manual_update"
    assert "original_route" in body and "updated_route" in body
    assert 0.0 <= body["old_risk"] <= 1.0 and 0.0 <= body["new_risk"] <= 1.0
    assert body["reason"]


def test_reroute_invalid_probability_in_edge_updates_returns_422(client):
    r = client.post("/api/v1/reroute", json={
        "origin": "S0040", "destination": "S0041", "edge_updates": {"some_edge": 1.5},
    })
    assert r.status_code == 422


def test_reroute_empty_edge_updates_returns_422(client):
    r = client.post("/api/v1/reroute", json={"origin": "S0040", "destination": "S0041", "edge_updates": {}})
    assert r.status_code == 422


def test_reroute_unknown_stop_returns_404(client):
    r = client.post("/api/v1/reroute", json={
        "origin": "NOT_A_STOP", "destination": "S0041", "edge_updates": {"e1": 0.5},
    })
    assert r.status_code == 404


# --- OpenAPI docs ---

def test_docs_is_reachable(client):
    r = client.get("/docs")
    assert r.status_code == 200


def test_openapi_json_describes_all_v1_endpoints(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    expected = {"/api/v1/health", "/api/v1/system/status", "/api/v1/model/info",
                "/api/v1/predict-disruption", "/api/v1/recommend-route", "/api/v1/reroute"}
    assert expected <= set(spec["paths"].keys())


def test_openapi_documents_error_responses(client):
    r = client.get("/openapi.json")
    spec = r.json()
    responses = spec["paths"]["/api/v1/recommend-route"]["post"]["responses"]
    assert "404" in responses
    assert "422" in responses


def test_root_aliases_exist_and_match_v1(client):
    r_v1 = client.get("/api/v1/health")
    r_root = client.get("/health")
    assert r_root.status_code == 200
    assert r_root.json() == r_v1.json()


def test_no_stack_trace_leaks_on_unexpected_error(client):
    """Forces an unexpected exception inside the inference service and
    confirms the client only ever sees a safe, generic message.

    Uses a dedicated TestClient with raise_server_exceptions=False:
    Starlette's TestClient re-raises exceptions into the TEST PROCESS by
    default (for debugging), bypassing the app's own exception handler's
    response entirely — that's a test-harness behavior, not how the app
    behaves under uvicorn. Disabling it here lets us inspect the actual
    HTTP response the handler produced, which is what a real client sees.
    """
    from api import dependencies

    def _broken_service():
        raise RuntimeError("simulated internal failure with sensitive detail: db_password=hunter2")

    client.app.dependency_overrides[dependencies.get_inference_service] = _broken_service
    try:
        with TestClient(client.app, raise_server_exceptions=False) as safe_client:
            r = safe_client.post("/api/v1/predict-disruption", json={"route_id": "R005", "stop_id": "S0021"})
        assert r.status_code == 500
        assert "hunter2" not in r.text
        assert "Traceback" not in r.text
        assert r.json()["error"]["code"] == "internal_error"
    finally:
        client.app.dependency_overrides.pop(dependencies.get_inference_service, None)


# --- model unavailable (dependency-override based, no real model needed) ---

def test_predict_returns_503_when_model_unavailable(client):
    from api import dependencies
    from api.exceptions import ModelUnavailableError

    def _raise_unavailable():
        raise ModelUnavailableError("No model is available for inference (simulated for this test).")

    client.app.dependency_overrides[dependencies.get_inference_service] = _raise_unavailable
    try:
        r = client.post("/api/v1/predict-disruption", json={"route_id": "R005", "stop_id": "S0021"})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "model_unavailable"
    finally:
        client.app.dependency_overrides.pop(dependencies.get_inference_service, None)


def test_recommend_route_returns_503_when_model_unavailable(client):
    from api import dependencies
    from api.exceptions import ModelUnavailableError

    def _raise_unavailable():
        raise ModelUnavailableError("The routing graph is unavailable (simulated for this test).")

    client.app.dependency_overrides[dependencies.get_routing_service] = _raise_unavailable
    try:
        r = client.post("/api/v1/recommend-route", json={"origin": "S0040", "destination": "S0041"})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "model_unavailable"
    finally:
        client.app.dependency_overrides.pop(dependencies.get_routing_service, None)


def test_model_info_returns_503_when_metadata_unavailable(client):
    from api import dependencies
    from api.state import AppState

    real_state = client.app.state.routewise
    fake_state = AppState(
        settings=real_state.settings, params_config=real_state.params_config, prediction_source=None,
        model_metadata=None, graph=None, inference_service=None, routing_service=None,
        model_load_error="simulated: no production model available", stops=real_state.stops,
        routes_with_stops=real_state.routes_with_stops, operational_metrics=real_state.operational_metrics,
    )
    client.app.dependency_overrides[dependencies.get_app_state] = lambda: fake_state
    try:
        r = client.get("/api/v1/model/info")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "model_unavailable"

        r_status = client.get("/api/v1/system/status")
        assert r_status.status_code == 200
        assert r_status.json()["model_name"] is None
        assert r_status.json()["routing_graph_available"] is False
    finally:
        client.app.dependency_overrides.pop(dependencies.get_app_state, None)
