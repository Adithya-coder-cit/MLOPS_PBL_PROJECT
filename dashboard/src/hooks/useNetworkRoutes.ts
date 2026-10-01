import { useEffect } from 'react'
import { listNetworkRoutes } from '../api/endpoints'
import { useAsync } from './useAsync'

export function useNetworkRoutes() {
  const { run, ...state } = useAsync((signal: AbortSignal) => listNetworkRoutes(signal))
  useEffect(() => {
    run().catch(() => {})
  }, [run])
  return { run, ...state }
}
