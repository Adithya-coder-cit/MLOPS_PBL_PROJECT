import { apiClient } from './client'
import type {
  DataSummaryResponse,
  EvaluationOverviewResponse,
  ExperimentsResponse,
  HealthResponse,
  ModelInfoResponse,
  PredictionRequest,
  PredictionResponse,
  RegistryOverviewResponse,
  RerouteRequest,
  RerouteResponse,
  RouteRecommendationRequest,
  RouteRecommendationResponse,
  RunDetailResponse,
  StopsResponse,
  SystemStatusResponse,
  TrainingStatusResponse,
} from './types'

export const getHealth = (signal?: AbortSignal) => apiClient.get<HealthResponse>('/health', signal)

export const getSystemStatus = (signal?: AbortSignal) =>
  apiClient.get<SystemStatusResponse>('/system/status', signal)

export const getModelInfo = (signal?: AbortSignal) => apiClient.get<ModelInfoResponse>('/model/info', signal)

export const listStops = (signal?: AbortSignal) => apiClient.get<StopsResponse>('/stops', signal)

export const predictDisruption = (payload: PredictionRequest, signal?: AbortSignal) =>
  apiClient.post<PredictionResponse>('/predict-disruption', payload, signal)

export const recommendRoute = (payload: RouteRecommendationRequest, signal?: AbortSignal) =>
  apiClient.post<RouteRecommendationResponse>('/recommend-route', payload, signal)

export const reroute = (payload: RerouteRequest, signal?: AbortSignal) =>
  apiClient.post<RerouteResponse>('/reroute', payload, signal)

// Internal engineering view only — never surfaced on the user-facing
// travel dashboard. See pages/admin/.
export const getExperiments = (signal?: AbortSignal) =>
  apiClient.get<ExperimentsResponse>('/admin/experiments', signal)

export const getTrainingStatus = (signal?: AbortSignal) =>
  apiClient.get<TrainingStatusResponse>('/admin/training/status', signal)

export const getEvaluationOverview = (signal?: AbortSignal) =>
  apiClient.get<EvaluationOverviewResponse>('/admin/evaluation', signal)

export const getDataSummary = (signal?: AbortSignal) =>
  apiClient.get<DataSummaryResponse>('/admin/data/summary', signal)

export const getRegistryOverview = (signal?: AbortSignal) =>
  apiClient.get<RegistryOverviewResponse>('/admin/registry', signal)

export const getRunDetail = (runId: string, signal?: AbortSignal) =>
  apiClient.get<RunDetailResponse>(`/admin/runs/${encodeURIComponent(runId)}`, signal)
