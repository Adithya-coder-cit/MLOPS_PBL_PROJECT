import { reroute } from '../api/endpoints'
import type { RerouteRequest } from '../api/types'
import { useAsync } from './useAsync'

export function useReroute() {
  return useAsync((request: RerouteRequest, signal: AbortSignal) => reroute(request, signal))
}
