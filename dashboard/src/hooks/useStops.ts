import { useEffect } from 'react'
import { listStops } from '../api/endpoints'
import { useAsync } from './useAsync'

export function useStops() {
  const { run, ...state } = useAsync((signal: AbortSignal) => listStops(signal))
  useEffect(() => {
    run().catch(() => {})
  }, [run])
  return { run, ...state }
}
