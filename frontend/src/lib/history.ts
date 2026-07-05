/** Lectura del historial desde Supabase (Fase 5).

Devuelve null cuando Supabase no está configurado o no hay sesión: la página
muestra el estado explicativo. RLS garantiza que cada usuario ve solo lo suyo.
*/

import { supabase } from './supabase'
import type { CleaningRules } from './types'

const BUCKET = 'datasets'

export type ActivityType =
  | 'carga'
  | 'estandarizacion'
  | 'limpieza'
  | 'analisis'
  | 'chat'
  | 'recomendacion'

export interface ActivityRow {
  id: string
  activity_type: ActivityType
  description: string
  dataset_id: string | null
  created_at: string
}

export interface DatasetRow {
  id: string
  name: string
  storage_path: string | null
  rows: number | null
  columns: number | null
  status: 'cargado' | 'estandarizado' | 'limpio' | 'error'
  quality: number | null
  created_at: string
}

export interface CleaningJobRow {
  rules: CleaningRules | null
}

async function hasSession(): Promise<boolean> {
  if (!supabase) return false
  const { data } = await supabase.auth.getSession()
  return Boolean(data.session)
}

/** 'error' ≠ "sin datos": la UI debe distinguir un fallo de Supabase (RLS,
 * migración faltante, red) de un historial legítimamente vacío. */
export type FetchOutcome<T> = T[] | null | 'error'

export async function fetchActivity(limit = 60): Promise<FetchOutcome<ActivityRow>> {
  if (!supabase || !(await hasSession())) return null
  const { data, error } = await supabase
    .from('activity_log')
    .select('id, activity_type, description, dataset_id, created_at')
    .order('created_at', { ascending: false })
    .limit(limit)
  if (error) {
    console.warn('[historial] No se pudo leer activity_log:', error.message)
    return 'error'
  }
  return data as ActivityRow[]
}

export async function fetchDatasets(limit = 20): Promise<FetchOutcome<DatasetRow>> {
  if (!supabase || !(await hasSession())) return null
  const { data, error } = await supabase
    .from('datasets')
    .select('id, name, storage_path, rows, columns, status, quality, created_at')
    .order('created_at', { ascending: false })
    .limit(limit)
  if (error) {
    console.warn('[historial] No se pudo leer datasets:', error.message)
    return 'error'
  }
  return data as DatasetRow[]
}

/** Descarga el archivo original desde Storage (RLS: solo la carpeta propia). */
export async function downloadDatasetFile(
  storagePath: string,
  name: string,
): Promise<File | null> {
  if (!supabase) return null
  const { data, error } = await supabase.storage.from(BUCKET).download(storagePath)
  if (error || !data) {
    console.warn('[historial] No se pudo descargar de Storage:', error?.message)
    return null
  }
  return new File([data], name, { type: data.type })
}

export async function fetchLatestCleaningRules(datasetId: string): Promise<CleaningRules | null> {
  if (!supabase || !(await hasSession())) return null
  const { data, error } = await supabase
    .from('cleaning_jobs')
    .select('rules')
    .eq('dataset_id', datasetId)
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle()
  if (error) {
    console.warn('[historial] No se pudieron leer reglas de limpieza:', error.message)
    return null
  }
  return (data as CleaningJobRow | null)?.rules ?? null
}
