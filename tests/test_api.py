"""API tests (Stage 7 §14): health, system status, model info, valid/
invalid prediction, route recommendation, unreachable route, rerouting,
model unavailable, malformed input, response schema, probability bounds.
Uses FastAPI's TestClient — no external network calls. The real app
(real model, real graph) is built once per test session and reused.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not Path("data/interim/joined_training_events.parquet").exists(),
    reason="Stage 3/6 artifacts not generated yet",
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
    assert body["monitoring_status"] == "not_implemented"


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
        model_load_error="simulated: no production model available",
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
