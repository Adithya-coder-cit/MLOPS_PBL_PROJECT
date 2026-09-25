import type { ApiErrorBody } from './types'

// Centralized API base URL — never hardcode localhost in a component.
// Falls back to the documented default only if the env var is unset
// (e.g. in a test environment that doesn't load .env.local).
const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000/api/v1'

export type ApiErrorCode =
  | 'invalid_input'
  | 'unknown_stop'
  | 'unknown_route'
  | 'unreachable_destination'
  | 'no_path_found'
  | 'invalid_route'
  | 'model_unavailable'
  | 'no_production_model'
  | 'inference_failure'
  | 'internal_error'
  | 'network_error'
  | 'unknown_error'

export class ApiError extends Error {
  readonly status: number
  readonly code: ApiErrorCode
  readonly detail: Record<string, unknown>

  constructor(status: number, code: ApiErrorCode, message: string, detail: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.detail = detail
  }
}

async function parseErrorBody(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | null = null
  try {
    body = (await response.json()) as ApiErrorBody
  } catch {
    // Response wasn't JSON — fall through to a generic message.
  }
  if (body?.error) {
    return new ApiError(response.status, body.error.code as ApiErrorCode, body.error.message, body.error.detail)
  }
  return new ApiError(response.status, 'unknown_error', `Request failed with status ${response.status}`)
}

interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  signal?: AbortSignal
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal } = options

  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') {
      throw cause
    }
    throw new ApiError(0, 'network_error', 'Could not reach the RouteWise API. Is the backend running?')
  }

  if (!response.ok) {
    throw await parseErrorBody(response)
  }

  return (await response.json()) as T
}

export const apiClient = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { method: 'GET', signal }),
  post: <T>(path: string, body: unknown, signal?: AbortSignal) => request<T>(path, { method: 'POST', body, signal }),
}

export const API_BASE_URL = BASE_URL
