import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./supabase', () => ({ supabase: null }))

import { apiDownload, apiGet, apiPost, apiPostJson, ApiError } from './api'

const busy = (retryAfter = '10', code: unknown = 'PROCESSING_BUSY') => new Response(
  JSON.stringify({ detail: 'Hay un calculo en curso.', code }),
  { status: 429, headers: { 'Content-Type': 'application/json', 'Retry-After': retryAfter } },
)

describe('processing capacity admission retries', () => {
  const request = vi.fn<typeof fetch>()

  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', request)
    request.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('waits Retry-After before replaying a multipart operation rejected before execution', async () => {
    request.mockResolvedValueOnce(busy()).mockResolvedValueOnce(Response.json({ rows: 42 }))
    const form = new FormData()
    form.set('storage_path', 'owner/source.csv')
    const result = apiPost('/clean', form)
    await vi.advanceTimersByTimeAsync(0)
    expect(request).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(9_999)
    expect(request).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(await result).toEqual({ rows: 42 })
    expect(request.mock.calls[1][1]?.body).toBe(form)
  })

  it('supports HTTP-date Retry-After and preserves a JSON request body', async () => {
    vi.setSystemTime(new Date('2026-09-10T12:00:00Z'))
    request.mockResolvedValueOnce(busy('Thu, 10 Sep 2026 12:00:02 GMT'))
      .mockResolvedValueOnce(Response.json({ restored: true }))
    const result = apiPostJson('/restore/dataset', { dataset_id: 'synthetic' })
    await vi.advanceTimersByTimeAsync(2_000)
    expect(await result).toEqual({ restored: true })
    expect(request.mock.calls[1][1]?.body).toBe('{"dataset_id":"synthetic"}')
  })

  it('stops after three retries and preserves the useful busy message', async () => {
    request.mockImplementation(async () => busy('1'))
    const result = apiGet('/consolidation/datasets/synthetic/inspect').catch(error => error)
    await vi.advanceTimersByTimeAsync(3_000)
    expect(await result).toMatchObject({ status: 429, message: 'Hay un calculo en curso.' })
    expect(request).toHaveBeenCalledTimes(4)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('allows cancellation during backoff without sending another operation', async () => {
    request.mockResolvedValueOnce(busy())
    const controller = new AbortController()
    const result = apiPost('/clean', new FormData(), { signal: controller.signal }).catch(error => error)
    await vi.advanceTimersByTimeAsync(0)
    controller.abort()
    expect(await result).toMatchObject({ status: 0, message: 'La solicitud fue cancelada.' })
    await vi.advanceTimersByTimeAsync(30_000)
    expect(request).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('shares the original total timeout across attempts and waiting', async () => {
    request.mockImplementation(async () => busy('1'))
    const result = apiPost('/metrics', new FormData(), { timeoutMs: 1_500 }).catch(error => error)
    await vi.advanceTimersByTimeAsync(1_500)
    expect(await result).toMatchObject({ status: 0 })
    expect(await result).toMatchObject({ message: expect.stringContaining('tardó demasiado') })
    expect(request).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([
    ['rate-limit without code', () => new Response('{"detail":"Too many requests"}', { status: 429, headers: { 'Retry-After': '1' } })],
    ['unrelated rate-limit code', () => busy('1', 'RATE_LIMITED')],
    ['invalid code shape', () => busy('1', ['PROCESSING_BUSY'])],
    ['invalid header', () => busy('not-a-date')],
    ['negative header', () => busy('-2')],
    ['excessive server delay', () => busy('3600')],
    ['missing header', () => new Response('{"code":"PROCESSING_BUSY"}', { status: 429 })],
    ['non-JSON response', () => new Response('<html>busy</html>', { status: 429, headers: { 'Retry-After': '1' } })],
    ['server error', () => new Response('{"code":"PROCESSING_BUSY"}', { status: 503, headers: { 'Retry-After': '1' } })],
  ])('does not replay %s', async (_name, response) => {
    request.mockResolvedValueOnce(response())
    const result = await apiPostJson('/restore/refresh', {}).catch(error => error)
    expect(result).toBeInstanceOf(ApiError)
    expect(request).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('does not repeat an operation after an ambiguous network failure', async () => {
    request.mockRejectedValueOnce(new TypeError('Network error'))
    await expect(apiPost('/clean', new FormData())).rejects.toMatchObject({ status: 0 })
    expect(request).toHaveBeenCalledTimes(1)
  })

  it('does not start a download after cancellation while the server is busy', async () => {
    request.mockResolvedValueOnce(busy())
    const controller = new AbortController()
    const result = apiDownload('/clean/download', new FormData(), 'clean.xlsx', {
      signal: controller.signal,
    }).catch(error => error)
    await vi.advanceTimersByTimeAsync(0)
    controller.abort()
    expect(await result).toMatchObject({ status: 0, message: 'La solicitud fue cancelada.' })
    expect(request).toHaveBeenCalledTimes(1)
  })
})
