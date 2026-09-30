import { getTrainingStatus } from '../api/endpoints'
import { useAsync } from './useAsync'

export function useTrainingStatus() {
  return useAsync((signal: AbortSignal) => getTrainingStatus(signal))
}
