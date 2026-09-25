import { apiClient } from './client'
import type {
  HealthResponse,
  ModelInfoResponse,
  PredictionRequest,
  PredictionResponse,
  RerouteRequest,
  RerouteResponse,
  RouteRecommendationRequest,
  RouteRecommendationResponse,
  StopsResponse,
  SystemStatusResponse,
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
