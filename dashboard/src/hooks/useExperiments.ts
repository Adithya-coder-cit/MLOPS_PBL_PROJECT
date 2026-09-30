import { getExperiments } from '../api/endpoints'
import { useAsync } from './useAsync'

// Not auto-run on mount — only fetched when the admin page is actually
// opened, so ordinary journey-planning users never trigger this call.
export function useExperiments() {
  return useAsync((signal: AbortSignal) => getExperiments(signal))
}
