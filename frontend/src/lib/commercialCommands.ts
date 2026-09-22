import { apiPostJson } from './api'

/** Keep uncertain operation IDs in this mounted view, never in browser storage. */
export function createCommercialPoster(send = apiPostJson) {
  const pending = new Map<string, string>()
  return async function post<T>(path: string, payload: Record<string, unknown>): Promise<T> {
    const key = JSON.stringify([path, payload])
    const operationId = pending.get(key) ?? crypto.randomUUID()
    pending.set(key, operationId)
    const result = await send<T>(path, { ...payload, operation_id: operationId })
    pending.delete(key)
    return result
  }
}
