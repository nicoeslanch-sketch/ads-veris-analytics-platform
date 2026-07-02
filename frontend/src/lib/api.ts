import { supabase } from './supabase'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export function buildFileForm(file: File, fields: Record<string, string> = {}): FormData {
  const form = new FormData()
  form.append('file', file)
  for (const [key, value] of Object.entries(fields)) {
    form.append(key, value)
  }
  return form
}

export async function apiPost<T>(path: string, body: FormData): Promise<T> {
  const session = supabase ? (await supabase.auth.getSession()).data.session : null
  const headers = new Headers()
  if (session?.access_token) {
    headers.set('Authorization', `Bearer ${session.access_token}`)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers,
    body,
  })

  if (!response.ok) {
    let message = `Error ${response.status}`
    try {
      const payload = (await response.json()) as { detail?: string }
      message = payload.detail ?? message
    } catch {
      message = response.statusText || message
    }
    throw new ApiError(message, response.status)
  }

  return response.json() as Promise<T>
}
