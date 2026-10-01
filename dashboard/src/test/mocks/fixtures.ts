import type {
  DataSummaryResponse,
  EvaluationOverviewResponse,
  ExperimentsResponse,
  NetworkRouteSchema,
  RegistryOverviewResponse,
  RouteRecommendationResponse,
  RouteSchema,
  RunDetailResponse,
  StopSchema,
  SystemStatusResponse,
  TrainingStatusResponse,
} from '../../api/types'

export const mockStops: StopSchema[] = [
  { stop_id: 'S0040', stop_name: 'Stop 40', lat: 13.01, lon: 80.2, zone_id: 'Z01', has_scheduled_service: true },
  { stop_id: 'S0041', stop_name: 'Stop 41', lat: 13.02, lon: 80.21, zone_id: 'Z01', has_scheduled_service: true },
  { stop_id: 'S0019', stop_name: 'Stop 19', lat: 13.03, lon: 80.22, zone_id: 'Z02', has_scheduled_service: true },
]

export const mockNetworkRoutes: NetworkRouteSchema[] = [
  { route_id: 'R011', direction_id: 0, transport_mode: 'bus', stop_ids: ['S0040', 'S0019', 'S0041'] },
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

export const mockExperiments: ExperimentsResponse = {
  available: true,
  reason: null,
  experiment_name: 'RouteWise-Disruption-Prediction',
  mlflow_tracking_uri: './mlruns',
  registered_model_name: 'RouteWise-Disruption-Model',
  runs: [
    {
      run_id: 'f1dc3eee9b6746c5885aa0827beda96a',
      run_name: 'xgboost_stage5',
      model_type: 'xgboost',
      status: 'FINISHED',
      lifecycle_stage: 'Candidate',
      registered_version: '6',
      start_time: '2026-09-26T20:15:02.531000',
      metrics: { test_f1: 0.5073575969404553, test_roc_auc: 0.7095617529904179 },
    },
  ],
}

export const mockTrainingStatus: TrainingStatusResponse = {
  real_data_model_ready: false,
  real_data_model_ready_reason: 'Weather feature coverage over the real ingested window is only 27.1% (minimum bar: 80%).',
  real_data_blocking_reasons: [
    'Weather feature coverage over the real ingested window is only 27.1% (minimum bar: 80%).',
    "No verified historical-label source exists for mode(s) ['rail', 'ferry'].",
  ],
  active_training_run: null,
  latest_completed_run: {
    training_timestamp: '2026-09-26T20:14:37',
    git_commit_sha: '2ac83a10a089e0c6ba0805f5e399aa58596f1253',
    dataset_label: 'Synthetic development dataset (DATA_MODE=demo) — not the real ingested dataset.',
    dataset_version: '0.1.0',
    train_records: 272160,
    validation_records: 58320,
    test_records: 58320,
    models: [
      {
        model_type: 'random_forest',
        feature_count: 22,
        test_f1: 0.502343994166059,
        test_roc_auc: 0.7070564687960897,
        registered_version: '5',
        run_id: 'efffa269e2ff454995313f042aae1751',
        gate_passed: false,
      },
      {
        model_type: 'xgboost',
        feature_count: 12,
        test_f1: 0.5073575969404553,
        test_roc_auc: 0.7095617529904179,
        registered_version: '6',
        run_id: 'f1dc3eee9b6746c5885aa0827beda96a',
        gate_passed: false,
      },
    ],
  },
  latest_retraining_check: {
    timestamp: '2026-09-29T22:42:55',
    dry_run: true,
    decision: 'DRY_RUN_OK',
  },
}

export const mockEvaluationOverview: EvaluationOverviewResponse = {
  available: true,
  reason: null,
  selection_metric: 'pr_auc',
  models: [
    {
      model_type: 'xgboost',
      validation_metrics: { accuracy: 0.6638, precision: 0.4111, recall: 0.6324, f1: 0.4983, roc_auc: 0.7059, pr_auc: 0.5045 },
      test_metrics: { accuracy: 0.6665, precision: 0.4233, recall: 0.633, f1: 0.5074, roc_auc: 0.7096, pr_auc: 0.5202 },
      confusion_matrix: { tn: 28853, fp: 13645, fn: 5806, tp: 10016 },
      threshold_sensitivity: [
        { threshold: 0.1, precision: 0.264, recall: 1.0, f1: 0.4178, n_predicted_positive: 58320 },
        { threshold: 0.5, precision: 0.4111, recall: 0.6324, f1: 0.4983, n_predicted_positive: 23686 },
      ],
      feature_importance: [
        { feature: 'day_period', gain: 787.03 },
        { feature: 'transfer_dependency', gain: 427.26 },
      ],
      roc_curve_available: false,
      pr_curve_available: false,
    },
    {
      model_type: 'random_forest',
      validation_metrics: { accuracy: 0.6658, precision: 0.4115, recall: 0.6181, f1: 0.4941, roc_auc: 0.7039, pr_auc: 0.5 },
      test_metrics: { accuracy: 0.6724, precision: 0.4272, recall: 0.6095, f1: 0.5023, roc_auc: 0.7071, pr_auc: 0.5156 },
      confusion_matrix: { tn: 29568, fp: 12930, fn: 6178, tp: 9644 },
      threshold_sensitivity: [{ threshold: 0.5, precision: 0.4115, recall: 0.6181, f1: 0.4941, n_predicted_positive: 23126 }],
      // Real scikit-learn feature-importance files use "importance", not
      // "gain" (that's XGBoost's key) — mirror that here.
      feature_importance: [{ feature: 'transfer_dependency', importance: 0.2647 }],
      roc_curve_available: false,
      pr_curve_available: false,
    },
  ],
  comparison: [
    { model: 'xgboost', f1: 0.5074, roc_auc: 0.7096 },
    { model: 'random_forest', f1: 0.5023, roc_auc: 0.7071 },
  ],
}

export const mockDataSummary: DataSummaryResponse = {
  available: true,
  reason: null,
  data_source: 'MBTA (transit) + NOAA GHCNh (weather)',
  total_real_records: 4808668,
  eligible_records: 3376547,
  excluded_records: 1432121,
  historical_feature_coverage: 0.6803095992486901,
  weather_coverage: 0.27113371104014666,
  weather_coverage_by_mode: { bus: 0.4018, metro: 0.1346, tram: 0.1246 },
  modes: ['bus', 'metro', 'tram'],
  splits: [
    { split: 'train', records: 1506834, positive_rate: 0.3247, modes: { tram: 805010, metro: 701824 } },
    { split: 'val', records: 328171, positive_rate: 0.2971, modes: { tram: 180878, metro: 147293 } },
    { split: 'test', records: 1541542, positive_rate: 0.2794, modes: { bus: 1200158, metro: 175567, tram: 165817 } },
  ],
  dvc_configured: true,
  real_dataset_ready: true,
}

export const mockRegistryOverview: RegistryOverviewResponse = {
  available: true,
  reason: null,
  total_models: 1,
  total_versions: 6,
  stage_counts: { Candidate: 6 },
  models: [
    {
      name: 'RouteWise-Disruption-Model',
      description: 'RouteWise disruption-probability classifier (XGBoost primary / Random Forest baseline).',
      latest_version: '6',
      latest_lifecycle_stage: 'Candidate',
      production_version: null,
      created: '2026-09-24T21:29:09.578000',
      versions: [
        {
          version: '6',
          lifecycle_stage: 'Candidate',
          is_production: false,
          test_f1: 0.5073575969404553,
          test_roc_auc: 0.7095617529904179,
          created: '2026-09-26T20:15:02.531000',
          run_id: 'f1dc3eee9b6746c5885aa0827beda96a',
        },
        {
          version: '5',
          lifecycle_stage: 'Candidate',
          is_production: false,
          test_f1: 0.502343994166059,
          test_roc_auc: 0.7070564687960897,
          created: '2026-09-26T20:14:55.323000',
          run_id: 'efffa269e2ff454995313f042aae1751',
        },
      ],
    },
  ],
}

export const mockRunDetail: RunDetailResponse = {
  run_id: 'f1dc3eee9b6746c5885aa0827beda96a',
  run_name: 'xgboost_stage5',
  status: 'FINISHED',
  start_time: '2026-09-26T20:15:02.531000',
  end_time: '2026-09-26T20:15:08.557000',
  params: { model_type: 'xgboost', hp_n_estimators: '500', hp_max_depth: '4' },
  metrics: { test_f1: 0.5073575969404553, test_roc_auc: 0.7095617529904179 },
  tags: { dataset_version: '0.1.0' },
  registered_version: '6',
  lifecycle_stage: 'Candidate',
  artifact_paths: ['evaluation/xgboost_confusion_matrix_test.png', 'evaluation/xgboost_evaluation.json'],
}

export { makeRoute }
