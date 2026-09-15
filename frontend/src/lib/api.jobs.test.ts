import { afterEach, beforeEach, expect, it, vi } from 'vitest'

vi.mock('./supabase', () => ({ supabase: null }))
import { apiPostJob } from './api'

const id = 'dq_0123456789abcdef0123456789abcdef'
const queued = { job_id: id, status: 'queued', result: null }
const request = vi.fn<typeof fetch>()

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('window', { setTimeout, clearTimeout })
  vi.stubGlobal('fetch', request)
  request.mockReset()
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

it('recovers polling after a server restart without posting a second computation', async () => {
  request.mockResolvedValueOnce(Response.json(queued))
    .mockResolvedValueOnce(Response.json({ detail: 'Restarting' }, { status: 503 }))
    .mockResolvedValueOnce(Response.json({ ...queued, status: 'completed', result: { total: 42 } }))
  const result = apiPostJob('/analysis/jobs/metrics', new FormData())
  await vi.advanceTimersByTimeAsync(5000)
  expect(await result).toEqual({ total: 42 })
  expect(request.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1)
  expect(String(request.mock.calls[2][0])).toContain(`/analysis/jobs/${id}`)
})

it('uses an already completed durable result immediately', async () => {
  request.mockResolvedValueOnce(Response.json({ ...queued, status: 'completed', result: { total: 42 } }))
  expect(await apiPostJob('/analysis/jobs/metrics', new FormData())).toEqual({ total: 42 })
  expect(request).toHaveBeenCalledTimes(1)
})

it('surfaces a failed durable job instead of treating missing results as zero', async () => {
  request.mockResolvedValueOnce(Response.json({ ...queued, status: 'failed', error: 'Fuente eliminada' }))
  await expect(apiPostJob('/analysis/jobs/metrics', new FormData())).rejects.toMatchObject({ message: 'Fuente eliminada' })
})

it('sends cancellation to the durable job identity', async () => {
  request.mockResolvedValueOnce(Response.json(queued)).mockResolvedValue(Response.json({ ...queued, status: 'cancelled' }))
  const controller = new AbortController()
  const result = apiPostJob('/analysis/jobs/metrics', new FormData(), { signal: controller.signal }).catch(error => error)
  await vi.advanceTimersByTimeAsync(0)
  controller.abort()
  await vi.advanceTimersByTimeAsync(0)
  expect(await result).toMatchObject({ status: 0 })
  expect(request.mock.calls.some(([url]) => String(url).endsWith(`/analysis/jobs/${id}/cancel`))).toBe(true)
})
