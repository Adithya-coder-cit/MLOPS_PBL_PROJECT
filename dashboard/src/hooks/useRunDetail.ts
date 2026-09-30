import { getRunDetail } from '../api/endpoints'
import { useAsync } from './useAsync'

export function useRunDetail() {
  return useAsync((runId: string, signal: AbortSignal) => getRunDetail(runId, signal))
}
