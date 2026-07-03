/** Cliente del motor de datos FastAPI.

Adjunta el JWT de la sesión Supabase en Authorization: Bearer.
Las claves secretas jamás viven aquí: el frontend solo conoce la URL pública
de la API (VITE_API_BASE_URL) y el token del usuario autenticado.
*/

import { supabase } from './supabase'

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

export async function apiPost<T>(path: string, form: FormData): Promise<T> {
  const token = await getAccessToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`

  const fullUrl = `${API_BASE_URL}${path}`
  console.log('[ADS] ▶ fetch', { API_BASE_URL, path, fullUrl, hasToken: !!token })

  let response: Response
  try {
    response = await fetch(fullUrl, { method: 'POST', headers, body: form })
  } catch (err) {
    console.error('[ADS] ✗ fetch error de red', err)
    throw new ApiError(
      0,
      'No se pudo contactar al motor de datos. ¿Está corriendo la API? (VITE_API_BASE_URL)',
    )
  }

  console.log('[ADS] ◀ response', {
    url: response.url,
    status: response.status,
    redirected: response.redirected,
    contentType: response.headers.get('content-type'),
  })
  const rawBody = await response.text()
  console.log('[ADS] body (raw):', rawBody.slice(0, 500))

  if (!response.ok) {
    let detail = `Error ${response.status} del motor de datos.`
    try {
      const body = JSON.parse(rawBody)
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // sin cuerpo JSON: se mantiene el mensaje genérico
    }
    throw new ApiError(response.status, detail)
  }
  try {
    return JSON.parse(rawBody) as T
  } catch {
    throw new ApiError(response.status, 'Respuesta inesperada del servidor (no es JSON válido).')
  }
}

export function buildFileForm(
  file: File,
  fields: Record<string, string> = {},
): FormData {
  const form = new FormData()
  form.append('file', file, file.name)
  for (const [key, value] of Object.entries(fields)) form.append(key, value)
  return form
}

/** POST con body JSON (para los endpoints /ai/*). */
export async function apiPostJson<T>(path: string, body: unknown): Promise<T> {
  const token = await getAccessToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  const fullUrl = `${API_BASE_URL}${path}`
  let response: Response
  try {
    response = await fetch(fullUrl, { method: 'POST', headers, body: JSON.stringify(body) })
  } catch {
    throw new ApiError(0, 'No se pudo contactar al servidor.')
  }
  const rawBody = await response.text()
  if (!response.ok) {
    let detail = `Error ${response.status} del servidor.`
    try {
      const parsed = JSON.parse(rawBody)
      if (typeof parsed.detail === 'string') detail = parsed.detail
    } catch { }
    throw new ApiError(response.status, detail)
  }
  try {
    return JSON.parse(rawBody) as T
  } catch {
    throw new ApiError(response.status, 'Respuesta inesperada del servidor.')
  }
}

/**
 * POST con body JSON y lectura de SSE (para /ai/chat).
 * Llama `onChunk` por cada fragmento de texto recibido.
 * Resuelve la promesa cuando el stream termina o rechaza en caso de error.
 */
export async function apiStream(
  path: string,
  body: unknown,
  onChunk: (text: string) => void,
): Promise<void> {
  const token = await getAccessToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  const fullUrl = `${API_BASE_URL}${path}`
  let response: Response
  try {
    response = await fetch(fullUrl, { method: 'POST', headers, body: JSON.stringify(body) })
  } catch {
    throw new ApiError(0, 'No se pudo contactar al servidor.')
  }
  if (!response.ok) {
    let detail = `Error ${response.status} del servidor.`
    try {
      const text = await response.text()
      const parsed = JSON.parse(text)
      if (typeof parsed.detail === 'string') detail = parsed.detail
    } catch { }
    throw new ApiError(response.status, detail)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new ApiError(0, 'No se pudo leer el stream del servidor.')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6).trim()
      if (data === '[DONE]') return
      try {
        const parsed = JSON.parse(data)
        if (parsed.error) throw new ApiError(500, parsed.error as string)
        if (typeof parsed.chunk === 'string') onChunk(parsed.chunk)
      } catch (e) {
        if (e instanceof ApiError) throw e
      }
    }
  }
}
