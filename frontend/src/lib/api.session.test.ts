import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const { getSession } = vi.hoisted(() => ({ getSession: vi.fn() }))
vi.mock('./supabase', () => ({ supabase: { auth: { getSession } } }))
import { apiDelete, apiDownload, apiGet, apiPost, apiPostJson, apiPutJson, apiStream } from './api'

const request = vi.fn<typeof fetch>()
beforeEach(() => {
  vi.useFakeTimers(); vi.stubGlobal('fetch', request)
  request.mockReset(); getSession.mockReset()
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it.each([
  ['get', () => apiGet('/security/session')],
  ['post', () => apiPost('/clean', new FormData())],
  ['download', () => apiDownload('/export', new FormData(), 'file.xlsx')],
  ['delete', () => apiDelete('/example')],
  ['json', () => apiPostJson('/example', {})],
  ['put', () => apiPutJson('/example', {})],
  ['stream', () => apiStream('/example', {}, () => {})],
])('%s cannot wait forever for session refresh or send an unauthenticated fallback', async (_, call) => {
  getSession.mockReturnValue(new Promise(() => {}))
  const result = call().catch(error => error)
  await vi.advanceTimersByTimeAsync(15_000)
  expect(await result).toMatchObject({ status: 0, message: expect.stringContaining('a tiempo') })
  expect(request).not.toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
})

it('cancellation releases timers and ignores a late token', async () => {
  let deliver!: (value: unknown) => void
  getSession.mockReturnValue(new Promise(resolve => { deliver = resolve }))
  const controller = new AbortController()
  const result = apiGet('/security/session', { signal: controller.signal }).catch(error => error)
  await vi.advanceTimersByTimeAsync(0)
  controller.abort()
  expect(await result).toMatchObject({ message: 'La solicitud fue cancelada.' })
  deliver({ data: { session: { access_token: 'late-test-token' } }, error: null })
  await vi.advanceTimersByTimeAsync(0)
  expect(request).not.toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
})

it('failed refresh stays closed without revealing provider details', async () => {
  getSession.mockResolvedValue({ error: { message: 'private diagnostic' }, data: { session: null } })
  await expect(apiGet('/security/session')).rejects.toMatchObject({ message: 'No pudimos verificar tu sesion. Vuelve a intentar.' })
  expect(request).not.toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
})

it('successful refresh sends the verified token and clears the timer', async () => {
  getSession.mockResolvedValue({ data: { session: { access_token: 'synthetic-token' } }, error: null })
  request.mockResolvedValue(Response.json({ ok: true }))
  expect(await apiGet('/security/session')).toEqual({ ok: true })
  expect(request.mock.calls[0][1]?.headers).toMatchObject({ Authorization: 'Bearer synthetic-token' })
  expect(vi.getTimerCount()).toBe(0)
})
