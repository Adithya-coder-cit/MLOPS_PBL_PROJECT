import { http, HttpResponse } from 'msw'
import {
  mockDataSummary,
  mockEvaluationOverview,
  mockExperiments,
  mockRecommendation,
  mockRegistryOverview,
  mockRunDetail,
  mockStops,
  mockSystemStatus,
  mockTrainingStatus,
} from './fixtures'

const BASE = 'http://localhost:8000/api/v1'

export const handlers = [
  http.get(`${BASE}/health`, () => HttpResponse.json({ status: 'ok', service: 'routewise-api', version: '0.1.0' })),
  http.get(`${BASE}/system/status`, () => HttpResponse.json(mockSystemStatus)),
  http.get(`${BASE}/stops`, () => HttpResponse.json({ stops: mockStops })),
  http.get(`${BASE}/model/info`, () =>
    HttpResponse.json({
      model_name: 'RouteWise-Disruption-Model',
      model_version: '4',
      model_type: 'xgboost',
      lifecycle_stage: 'Candidate',
      mlflow_run_id: 'abc123',
      git_commit_sha: 'deadbeef',
      dataset_version: '0.1.0',
      feature_manifest_version: '1.0.0',
      training_timestamp: '1700000000000',
      validation_metrics: { precision: 0.41, recall: 0.63, f1: 0.5, roc_auc: 0.71, pr_auc: 0.5 },
      test_metrics: { precision: 0.42, recall: 0.63, f1: 0.51, roc_auc: 0.71, pr_auc: 0.52 },
      is_production_model: false,
    }),
  ),
  http.get(`${BASE}/admin/experiments`, () => HttpResponse.json(mockExperiments)),
  http.get(`${BASE}/admin/training/status`, () => HttpResponse.json(mockTrainingStatus)),
  http.get(`${BASE}/admin/evaluation`, () => HttpResponse.json(mockEvaluationOverview)),
  http.get(`${BASE}/admin/data/summary`, () => HttpResponse.json(mockDataSummary)),
  http.get(`${BASE}/admin/registry`, () => HttpResponse.json(mockRegistryOverview)),
  http.get(`${BASE}/admin/runs/:runId`, () => HttpResponse.json(mockRunDetail)),
  http.post(`${BASE}/recommend-route`, () => HttpResponse.json(mockRecommendation)),
  http.post(`${BASE}/reroute`, () =>
    HttpResponse.json({
      data_source: 'manual_update',
      original_route: mockRecommendation.candidates[0],
      updated_route: mockRecommendation.candidates[1],
      changed: true,
      old_risk: 0.82,
      new_risk: 0.9,
      old_score: -0.491,
      new_score: -0.1,
      reason: "Recommendation changed from route A to route B under the 'high_risk' policy.",
    }),
  ),
]
