import { useCallback, useEffect, useRef, useState } from 'react'

export type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'

export interface AsyncState<T> {
  status: AsyncStatus
  data: T | null
  error: unknown
}

/**
 * Wraps a single async call with idle/loading/success/error state. Does
 * NOT auto-run on mount — call `run()` explicitly (see useEffect callers).
 * Aborts the in-flight request if a new one starts before it resolves,
 * so a slow first response can never overwrite a newer one.
 */
export function useAsync<Args extends unknown[], T>(fn: (...args: [...Args, AbortSignal]) => Promise<T>) {
  const [state, setState] = useState<AsyncState<T>>({ status: 'idle', data: null, error: null })
  const controllerRef = useRef<AbortController | null>(null)
  const fnRef = useRef(fn)

  useEffect(() => {
    fnRef.current = fn
  }, [fn])

  useEffect(() => () => controllerRef.current?.abort(), [])

  const run = useCallback(async (...args: Args) => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    setState({ status: 'loading', data: null, error: null })
    try {
      const data = await fnRef.current(...args, controller.signal)
      if (controller.signal.aborted) return
      setState({ status: 'success', data, error: null })
      return data
    } catch (error) {
      if (controller.signal.aborted) return
      setState({ status: 'error', data: null, error })
      throw error
    }
  }, [])

  const reset = useCallback(() => setState({ status: 'idle', data: null, error: null }), [])

  return { ...state, run, reset }
}
