/** Lectura del historial desde Supabase (Fase 5).

Devuelve null cuando Supabase no está configurado o no hay sesión: la página
muestra el estado explicativo. RLS garantiza que cada usuario ve solo lo suyo.
*/

import { supabase } from './supabase'
import {
  DEFAULT_CLEANING_OPTIONS,
  type CleaningOptions,
  type CleaningRules,
} from './types'

const BUCKET = 'datasets'

export type ActivityType =
  | 'carga'
  | 'estandarizacion'
  | 'limpieza'
  | 'analisis'
  | 'chat'
  | 'recomendacion'
  | 'eliminacion'

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
  source: string
  storage_path: string | null
  rows: number | null
  columns: number | null
  status: 'cargado' | 'estandarizado' | 'limpio' | 'error'
  quality: number | null
  created_at: string
}

export interface CleaningJobRow {
  rules: CleaningRules | null
  options?: CleaningOptions | null
}

export interface CleaningConfig {
  rules: CleaningRules | null
  options: CleaningOptions
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

// Fase 11 §14.3: el Plan Gold conserva hasta 50 archivos — el listado debe alcanzarlos.
export async function fetchDatasets(limit = 50): Promise<FetchOutcome<DatasetRow>> {
  if (!supabase || !(await hasSession())) return null
  const { data, error } = await supabase
    .from('datasets')
    .select('id, name, source, storage_path, rows, columns, status, quality, created_at')
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

export async function fetchLatestCleaningConfig(datasetId: string): Promise<CleaningConfig | null> {
  if (!supabase || !(await hasSession())) return null
  const { data, error } = await supabase
    .from('cleaning_jobs')
    .select('rules, options')
    .eq('dataset_id', datasetId)
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle()
  if (error) {
    // Compatibilidad durante el despliegue: si 0012 aún no se aplicó, se
    // recuperan las reglas antiguas y la decisión segura queda en false.
    const fallback = await supabase
      .from('cleaning_jobs')
      .select('rules')
      .eq('dataset_id', datasetId)
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle()
    if (fallback.error) {
      console.warn('[historial] No se pudo leer la configuración de limpieza:', error.message)
      return null
    }
    const legacy = fallback.data as CleaningJobRow | null
    return legacy
      ? { rules: legacy.rules, options: DEFAULT_CLEANING_OPTIONS }
      : null
  }
  const row = data as CleaningJobRow | null
  return row
    ? { rules: row.rules, options: row.options ?? DEFAULT_CLEANING_OPTIONS }
    : null
}

/** @deprecated Usa fetchLatestCleaningConfig para no perder las opciones. */
export async function fetchLatestCleaningRules(datasetId: string): Promise<CleaningRules | null> {
  return (await fetchLatestCleaningConfig(datasetId))?.rules ?? null
}
