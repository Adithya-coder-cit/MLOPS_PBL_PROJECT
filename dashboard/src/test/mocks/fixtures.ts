import type { RouteRecommendationResponse, RouteSchema, StopSchema, SystemStatusResponse } from '../../api/types'

export const mockStops: StopSchema[] = [
  { stop_id: 'S0040', stop_name: 'Stop 40', lat: 13.01, lon: 80.2, zone_id: 'Z01' },
  { stop_id: 'S0041', stop_name: 'Stop 41', lat: 13.02, lon: 80.21, zone_id: 'Z01' },
  { stop_id: 'S0019', stop_name: 'Stop 19', lat: 13.03, lon: 80.22, zone_id: 'Z02' },
]

export const mockSystemStatus: SystemStatusResponse = {
  application_version: '0.1.0',
  api_version: 'v1',
  model_name: 'RouteWise-Disruption-Model',
  model_version: '4',
  model_lifecycle_stage: 'Candidate',
  is_production_model: false,
  production_model_available: false,
  configured_model_source: 'candidate',
  dataset_version: '0.1.0',
  feature_manifest_version: '1.0.0',
  routing_graph_available: true,
  routing_engine_version: '1.0.0',
  environment: 'test',
  monitoring: {
    available: true,
    last_run_at: '2026-09-25T22:16:12',
    dataset_type: 'DEVELOPMENT/DEMO',
    data_quality_status: 'PASS',
    data_drift_status: 'DRIFT_DETECTED',
    prediction_drift_status: 'NO_DRIFT',
    performance_status: 'OK',
    decision: 'REVIEW_REQUIRED',
    operational: {
      request_count: 12,
      successful_requests: 11,
      failed_requests: 1,
      prediction_errors: 0,
      route_recommendation_errors: 1,
      latency_ms: { mean: 42.5, p50: 30, p95: 120, max: 150, sample_size: 12 },
      model_load_status: 'available',
      scope: 'local/development process-lifetime counters — reset on API restart, not distributed',
    },
  },
  dvc_configured: true,
  mlflow_reachable: true,
  ci_cd_configured: true,
  risk_label_thresholds: { moderate_threshold: 0.2, high_threshold: 0.4 },
}

function makeRoute(overrides: Partial<RouteSchema>): RouteSchema {
  return {
    route_id: 'S0040-S0041-abc123',
    origin: 'S0040',
    destination: 'S0041',
    transport_modes: ['bus'],
    stops: ['S0040', 'S0019', 'S0041'],
    segments: [
      {
        edge_id: 'R011:1:S0040->S0019',
        from_stop: 'S0040',
        to_stop: 'S0019',
        route_id: 'R011',
        trip_id: 'T000540',
        transport_mode: 'bus',
        travel_time: 12,
        cost: 5.75,
        disruption_probability: 0.36,
        reliability: 0.64,
        is_transfer_point: false,
      },
      {
        edge_id: 'R005:1:S0019->S0041',
        from_stop: 'S0019',
        to_stop: 'S0041',
        route_id: 'R005',
        trip_id: 'T000252',
        transport_mode: 'bus',
        travel_time: 15,
        cost: 3.88,
        disruption_probability: 0.29,
        reliability: 0.71,
        is_transfer_point: true,
      },
    ],
    total_time: 43,
    total_cost: 21.38,
    reliability: 0.18,
    disruption_risk: 0.82,
    transfer_count: 2,
    score: -0.491,
    decision_policy: 'high_risk',
    data_version: '0.1.0',
    explanation: "Selected under the 'high_risk' decision policy: 43.0 min total travel time.",
    model_metadata: {
      model_name: 'RouteWise-Disruption-Model',
      model_version: '4',
      lifecycle_stage: 'Candidate',
      is_production_model: false,
      model_source_warning: 'This route was scored using a NON-PRODUCTION (candidate) model.',
    },
    ...overrides,
  }
}

export const mockRecommendation: RouteRecommendationResponse = {
  origin: 'S0040',
  destination: 'S0041',
  candidates: [
    makeRoute({}),
    makeRoute({ route_id: 'S0040-S0041-def456', total_time: 51, total_cost: 20.63, score: -0.109 }),
  ],
  selected: makeRoute({}),
}

export { makeRoute }
