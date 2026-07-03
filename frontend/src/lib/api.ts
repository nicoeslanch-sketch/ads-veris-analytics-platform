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

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers,
      body: form,
    })
  } catch {
    throw new ApiError(
      0,
      'No se pudo contactar al motor de datos. ¿Está corriendo la API? (VITE_API_BASE_URL)',
    )
  }

  if (!response.ok) {
    let detail = `Error ${response.status} del motor de datos.`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // sin cuerpo JSON: se mantiene el mensaje genérico
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
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
