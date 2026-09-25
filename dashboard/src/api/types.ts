// Mirrors api/schemas/*.py exactly. Keep these two in sync by hand — no
// codegen step exists yet (see README "Future Work").

export interface HealthResponse {
  status: string
  service: string
  version: string
}

export interface RiskLabelThresholds {
  moderate_threshold: number
  high_threshold: number
}

export interface SystemStatusResponse {
  application_version: string
  api_version: string
  model_name: string | null
  model_version: string | null
  model_lifecycle_stage: string | null
  is_production_model: boolean
  production_model_available: boolean
  configured_model_source: string
  dataset_version: string | null
  feature_manifest_version: string | null
  routing_graph_available: boolean
  routing_engine_version: string
  environment: string
  monitoring_status: string
  dvc_configured: boolean
  mlflow_reachable: boolean
  ci_cd_configured: boolean
  risk_label_thresholds: RiskLabelThresholds
}

export interface ModelInfoResponse {
  model_name: string
  model_version: string
  model_type: string
  lifecycle_stage: string | null
  mlflow_run_id: string
  git_commit_sha: string | null
  dataset_version: string | null
  feature_manifest_version: string | null
  training_timestamp: string | null
  validation_metrics: Record<string, number>
  test_metrics: Record<string, number>
  is_production_model: boolean
}

export interface StopSchema {
  stop_id: string
  stop_name: string
  lat: number
  lon: number
  zone_id: string
}

export interface StopsResponse {
  stops: StopSchema[]
}

export interface ModelMetadataSchema {
  model_name: string
  model_version: string
  lifecycle_stage: string | null
  is_production_model: boolean
  model_source_warning: string | null
}

export interface PredictionRequest {
  route_id: string
  stop_id: string
  query_datetime?: string
  precipitation_mm?: number
  temperature_c?: number
  visibility_km?: number
}

export interface PredictionResponse {
  disruption_probability: number
  predicted_class: number
  decision_threshold: number
  feature_timestamp: string
  explanation: string
  top_factors: string[]
  model_metadata: ModelMetadataSchema
}

export interface SegmentSchema {
  edge_id: string
  from_stop: string
  to_stop: string
  route_id: string
  trip_id: string
  transport_mode: string
  travel_time: number
  cost: number
  disruption_probability: number
  reliability: number
  is_transfer_point: boolean
}

export interface RouteSchema {
  route_id: string
  origin: string
  destination: string
  transport_modes: string[]
  stops: string[]
  segments: SegmentSchema[]
  total_time: number
  total_cost: number
  reliability: number
  disruption_risk: number
  transfer_count: number
  score: number
  decision_policy: string
  data_version: string | null
  explanation: string
  model_metadata: ModelMetadataSchema
}

export interface RouteRecommendationRequest {
  origin: string
  destination: string
  departure_time?: string
  top_n?: number
}

export interface RouteRecommendationResponse {
  origin: string
  destination: string
  candidates: RouteSchema[]
  selected: RouteSchema
}

export interface RerouteRequest {
  origin: string
  destination: string
  edge_updates: Record<string, number>
  top_n?: number
}

export interface RerouteResponse {
  data_source: string
  original_route: RouteSchema
  updated_route: RouteSchema
  changed: boolean
  old_risk: number
  new_risk: number
  old_score: number
  new_score: number
  reason: string
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    detail: Record<string, unknown>
  }
}
