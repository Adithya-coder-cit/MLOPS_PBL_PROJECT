import { getDataSummary } from '../api/endpoints'
import { useAsync } from './useAsync'

export function useDataSummary() {
  return useAsync((signal: AbortSignal) => getDataSummary(signal))
}
