import { getEvaluationOverview } from '../api/endpoints'
import { useAsync } from './useAsync'

export function useEvaluationOverview() {
  return useAsync((signal: AbortSignal) => getEvaluationOverview(signal))
}
