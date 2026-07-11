/** Cliente del motor de datos FastAPI.

Adjunta el JWT de la sesión Supabase en Authorization: Bearer.
Las claves secretas jamás viven aquí: el frontend solo conoce la URL pública
de la API (VITE_API_BASE_URL) y el token del usuario autenticado.
*/

import { supabase } from './supabase'

// En desarrollo cae a localhost; en producción la variable es obligatoria
// (sin fallback silencioso: un error claro evita horas de diagnóstico).
const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, '') ??
  (import.meta.env.DEV ? 'http://localhost:8000' : '')

/** Timeouts (Fase 11 §11.1): una petición colgada ya no deja la página
 * "cargando" para siempre. El primer procesamiento de un archivo grande
 * puede tardar — el pipeline recibe margen amplio; las lecturas, poco. */
const PIPELINE_TIMEOUT_MS = 240_000
const JSON_TIMEOUT_MS = 90_000
const GET_TIMEOUT_MS = 60_000

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

function connectionError(err: unknown, fallback: string): ApiError {
  if (err instanceof DOMException && err.name === 'AbortError') {
    return new ApiError(0, 'La solicitud tardó demasiado y se canceló. Vuelve a intentar.')
  }
  return new ApiError(0, fallback)
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

function requireBase(): string {
  if (!API_BASE_URL) {
    throw new ApiError(
      0,
      'Falta configurar VITE_API_BASE_URL en el entorno de despliegue (Vercel).',
    )
  }
  return API_BASE_URL
}

async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

export async function apiPost<T>(
  path: string,
  form: FormData,
  timeoutMs = PIPELINE_TIMEOUT_MS,
): Promise<T> {
  const token = await getAccessToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`

  const fullUrl = `${requireBase()}${path}`
  let response: Response
  try {
    response = await fetchWithTimeout(fullUrl, { method: 'POST', headers, body: form }, timeoutMs)
  } catch (err) {
    throw connectionError(
      err,
      'No se pudo contactar al motor de datos. ¿Está corriendo la API? (VITE_API_BASE_URL)',
    )
  }

  const rawBody = await response.text()
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

export function buildDatasetForm(
  file: File,
  storagePath: string | null,
  fields: Record<string, string> = {},
): FormData {
  const form = new FormData()
  if (storagePath) {
    form.append('storage_path', storagePath)
  } else {
    form.append('file', file, file.name)
  }
  for (const [key, value] of Object.entries(fields)) form.append(key, value)
  return form
}

/** POST multipart que devuelve un archivo descargable (binario). Dispara el diálogo del navegador. */
export async function apiDownload(path: string, form: FormData, fallbackFilename: string): Promise<void> {
  const token = await getAccessToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`

  const fullUrl = `${requireBase()}${path}`
  let response: Response
  try {
    response = await fetchWithTimeout(fullUrl, { method: 'POST', headers, body: form }, PIPELINE_TIMEOUT_MS)
  } catch (err) {
    throw connectionError(err, 'No se pudo contactar al servidor.')
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
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const match = disposition.match(/filename="([^"]+)"/)
  const filename = match ? match[1] : fallbackFilename
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/** GET con JWT (para endpoints de estado como /ai/usage). */
export async function apiGet<T>(path: string): Promise<T> {
  const token = await getAccessToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`

  const fullUrl = `${requireBase()}${path}`
  let response: Response
  try {
    response = await fetchWithTimeout(fullUrl, { headers }, GET_TIMEOUT_MS)
  } catch (err) {
    throw connectionError(err, 'No se pudo contactar al servidor.')
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

/** POST con body JSON (para los endpoints /ai/*). */
export async function apiPostJson<T>(path: string, body: unknown): Promise<T> {
  const token = await getAccessToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  const fullUrl = `${requireBase()}${path}`
  let response: Response
  try {
    response = await fetchWithTimeout(
      fullUrl,
      { method: 'POST', headers, body: JSON.stringify(body) },
      JSON_TIMEOUT_MS,
    )
  } catch (err) {
    throw connectionError(err, 'No se pudo contactar al servidor.')
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

  const fullUrl = `${requireBase()}${path}`
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
