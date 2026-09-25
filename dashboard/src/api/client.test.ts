import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../test/mocks/server'
import { apiClient, ApiError } from './client'

const BASE = 'http://localhost:8000/api/v1'

describe('apiClient', () => {
  it('parses a successful JSON response', async () => {
    server.use(http.get(`${BASE}/health`, () => HttpResponse.json({ status: 'ok', service: 'x', version: '1' })))
    const result = await apiClient.get<{ status: string }>('/health')
    expect(result.status).toBe('ok')
  })

  it('throws a typed ApiError with the backend error code on a 4xx/5xx response', async () => {
    server.use(
      http.post(`${BASE}/predict-disruption`, () =>
        HttpResponse.json(
          { error: { code: 'unknown_stop', message: "Unknown stop_id 'X'", detail: { stop_id: 'X' } } },
          { status: 404 },
        ),
      ),
    )
    await expect(apiClient.post('/predict-disruption', {})).rejects.toMatchObject({
      status: 404,
      code: 'unknown_stop',
    })
  })

  it('throws a network_error ApiError when the request fails outright', async () => {
    server.use(http.get(`${BASE}/health`, () => HttpResponse.error()))
    const error: unknown = await apiClient.get('/health').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('network_error')
  })

  it('never throws a raw, unparsed error for a non-JSON error body', async () => {
    server.use(http.get(`${BASE}/health`, () => new HttpResponse('<html>error</html>', { status: 500 })))
    const error: unknown = await apiClient.get('/health').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(500)
  })
})
