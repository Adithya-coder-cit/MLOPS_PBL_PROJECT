import { getRegistryOverview } from '../api/endpoints'
import { useAsync } from './useAsync'

export function useRegistryOverview() {
  return useAsync((signal: AbortSignal) => getRegistryOverview(signal))
}
