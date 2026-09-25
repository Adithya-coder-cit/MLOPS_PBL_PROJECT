import { recommendRoute } from '../api/endpoints'
import type { RouteRecommendationRequest } from '../api/types'
import { useAsync } from './useAsync'

export function useRouteSearch() {
  return useAsync((request: RouteRecommendationRequest, signal: AbortSignal) => recommendRoute(request, signal))
}
