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

export interface OperationalLatency {
  mean: number | null
  p50: number | null
  p95: number | null
  max: number | null
  sample_size: number
}

export interface OperationalSnapshot {
  request_count: number
  successful_requests: number
  failed_requests: number
  prediction_errors: number
  route_recommendation_errors: number
  latency_ms: OperationalLatency
  model_load_status: string
  scope: string
}

// data_quality/data_drift/prediction_drift/performance/decision are each
// "NOT_RUN" until a monitoring run has ever completed (Stage 9) — never a
// fabricated "healthy" default. See src/monitoring/schemas.py.
export interface MonitoringStatusResponse {
  available: boolean
  last_run_at: string | null
  dataset_type: string | null
  data_quality_status: string
  data_drift_status: string
  prediction_drift_status: string
  performance_status: string
  decision: string
  operational: OperationalSnapshot
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
  monitoring: MonitoringStatusResponse
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

export interface ExperimentRunSchema {
  run_id: string
  run_name: string | null
  model_type: string | null
  status: string
  lifecycle_stage: string | null
  registered_version: string | null
  start_time: string | null
  metrics: Record<string, number>
}

export interface ExperimentsResponse {
  available: boolean
  reason: string | null
  experiment_name: string
  mlflow_tracking_uri: string
  registered_model_name: string
  runs: ExperimentRunSchema[]
}

// --- training status ---

export interface TrainedModelSummarySchema {
  model_type: string
  feature_count: number | null
  test_f1: number | null
  test_roc_auc: number | null
  registered_version: string | null
  run_id: string | null
  gate_passed: boolean | null
}

export interface LatestCompletedRunSchema {
  training_timestamp: string | null
  git_commit_sha: string | null
  dataset_label: string
  dataset_version: string | null
  train_records: number | null
  validation_records: number | null
  test_records: number | null
  models: TrainedModelSummarySchema[]
}

export interface LatestRetrainingCheckSchema {
  timestamp: string | null
  dry_run: boolean | null
  decision: string | null
}

export interface TrainingStatusResponse {
  real_data_model_ready: boolean | null
  real_data_model_ready_reason: string | null
  real_data_blocking_reasons: string[]
  active_training_run: null
  latest_completed_run: LatestCompletedRunSchema | null
  latest_retraining_check: LatestRetrainingCheckSchema | null
}

// --- evaluation ---

export interface EvaluationModelSchema {
  model_type: string
  validation_metrics: Record<string, number>
  test_metrics: Record<string, number>
  confusion_matrix: { tn: number; fp: number; fn: number; tp: number } | null
  threshold_sensitivity: Record<string, number>[] | null
  // XGBoost's saved importance uses the key "gain"; scikit-learn's (random
  // forest) uses "importance" — genuinely different real metrics from
  // different libraries, never normalized into one fabricated name.
  feature_importance: { feature: string; gain?: number; importance?: number }[] | null
  roc_curve_available: boolean
  pr_curve_available: boolean
}

export interface EvaluationOverviewResponse {
  available: boolean
  reason: string | null
  selection_metric: string | null
  models: EvaluationModelSchema[]
  comparison: Record<string, unknown>[]
}

// --- data summary ---

export interface DataSplitSchema {
  split: string
  records: number
  positive_rate: number | null
  modes: Record<string, number>
}

export interface DataSummaryResponse {
  available: boolean
  reason: string | null
  data_source: string
  total_real_records: number | null
  eligible_records: number | null
  excluded_records: number | null
  historical_feature_coverage: number | null
  weather_coverage: number | null
  weather_coverage_by_mode: Record<string, number>
  modes: string[]
  splits: DataSplitSchema[]
  dvc_configured: boolean
  real_dataset_ready: boolean | null
}

// --- model registry ---

export interface ModelVersionSchema {
  version: string
  lifecycle_stage: string
  is_production: boolean
  test_f1: number | null
  test_roc_auc: number | null
  created: string | null
  run_id: string
}

export interface RegisteredModelSchema {
  name: string
  description: string | null
  latest_version: string | null
  latest_lifecycle_stage: string | null
  production_version: string | null
  created: string | null
  versions: ModelVersionSchema[]
}

export interface RegistryOverviewResponse {
  available: boolean
  reason: string | null
  total_models: number
  total_versions: number
  stage_counts: Record<string, number>
  models: RegisteredModelSchema[]
}

// --- run detail ---

export interface RunDetailResponse {
  run_id: string
  run_name: string | null
  status: string
  start_time: string | null
  end_time: string | null
  params: Record<string, string>
  metrics: Record<string, number>
  tags: Record<string, string>
  registered_version: string | null
  lifecycle_stage: string | null
  artifact_paths: string[]
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    detail: Record<string, unknown>
  }
}
