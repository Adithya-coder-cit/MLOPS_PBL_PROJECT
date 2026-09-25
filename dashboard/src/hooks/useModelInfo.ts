import { useEffect } from 'react'
import { getModelInfo } from '../api/endpoints'
import { useAsync } from './useAsync'

export function useModelInfo() {
  const { run, ...state } = useAsync((signal: AbortSignal) => getModelInfo(signal))
  useEffect(() => {
    run().catch(() => {})
  }, [run])
  return { run, ...state }
}
