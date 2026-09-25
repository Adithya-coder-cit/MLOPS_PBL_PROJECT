import { useEffect } from 'react'
import { getSystemStatus } from '../api/endpoints'
import { useAsync } from './useAsync'

export function useSystemStatus() {
  const { run, ...state } = useAsync((signal: AbortSignal) => getSystemStatus(signal))
  useEffect(() => {
    run().catch(() => {
      // Surfaced via state.error / state.status — nothing further to do here.
    })
  }, [run])
  return { run, ...state }
}
