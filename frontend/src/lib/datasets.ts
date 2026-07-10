/** Persistencia del pipeline en Supabase (Storage + tablas de la migración 0002).

Todas las funciones son "best-effort": si Supabase no está configurado o no hay
sesión, no hacen nada y devuelven null. El pipeline funciona igual en memoria;
la persistencia agrega historial y permite retomar archivos después.
*/

import { supabase } from './supabase'
import type { CleanResult, CleaningRules, StandardizeResult } from './types'

const BUCKET = 'datasets'
export type DatasetSource = 'excel_csv' | 'google_sheets'

async function getUserId(): Promise<string | null> {
  if (!supabase) return null
  const { data } = await supabase.auth.getSession()
  return data.session?.user.id ?? null
}

/** Sube el archivo a Storage bajo {user_id}/... y devuelve el storage_path. */
export async function uploadToStorage(file: File): Promise<string | null> {
  const userId = await getUserId()
  if (!supabase || !userId) return null
  const path = `${userId}/${Date.now()}_${file.name.replace(/[^\w.\-]+/g, '_')}`
  const { error } = await supabase.storage.from(BUCKET).upload(path, file)
  if (error) {
    // Best-effort, pero el motivo debe ser visible para diagnosticar (RLS, bucket, red)
    console.warn('[persistencia] Falló la subida a Storage:', error.message)
    return null
  }
  return path
}

export async function insertDataset(
  file: File,
  storagePath: string | null,
  source: DatasetSource = 'excel_csv',
): Promise<string | null> {
  const userId = await getUserId()
  if (!supabase || !userId) return null
  const { data, error } = await supabase
    .from('datasets')
    .insert({
      user_id: userId,
      name: file.name,
      source,
      storage_path: storagePath,
      status: 'cargado',
    })
    .select('id')
    .single()
  if (error) {
    console.warn('[persistencia] Falló el insert en datasets:', error.message)
    return null
  }
  try { await logActivity('carga', `Archivo cargado: ${file.name}`, data.id) } catch { /* best-effort */ }
  return data.id as string
}

export async function markStandardized(
  datasetId: string | null,
  result: StandardizeResult,
): Promise<boolean> {
  if (!supabase || !datasetId) return false
  try {
    const { error: datasetError } = await supabase
      .from('datasets')
      .update({ rows: result.filas, columns: result.columnas, status: 'estandarizado' })
      .eq('id', datasetId)
    if (datasetError) {
      console.warn('[persistencia] Falló el update de datasets:', datasetError.message)
      return false
    }
    const columns = result.preview.columnas.map((name) => ({
      dataset_id: datasetId,
      original_name: name,
      normalized_name: name,
      detected_type: result.column_types[name] ?? 'texto',
      mapped_role:
        Object.entries(result.mapeo).find(([, col]) => col === name)?.[0] ?? null,
    }))
    if (columns.length > 0) {
      const { error: columnsError } = await supabase.from('dataset_columns').insert(columns)
      if (columnsError) {
        console.warn('[persistencia] Falló el insert en dataset_columns:', columnsError.message)
        return false
      }
    }
    try {
      await logActivity('estandarizacion', `Estandarización aplicada: ${result.archivo}`, datasetId)
    } catch (err) {
      console.warn('[persistencia] No se pudo registrar actividad de estandarizacion:', err)
    }
    return true
  } catch (err) {
    // best-effort: fallo en persistencia no bloquea el pipeline
    console.warn('[persistencia] Error de red guardando la estandarización:', err)
    return false
  }
}

/** Best-effort: la limpieza YA se aplicó en la API; un fallo aquí solo significa
 * que no quedó en el historial — jamás debe mostrarse como error de limpieza.
 * Devuelve false si algo no se pudo guardar (la UI puede avisar suave). */
export async function saveCleaningJob(
  datasetId: string | null,
  rules: CleaningRules,
  result: CleanResult,
): Promise<boolean> {
  const userId = await getUserId()
  if (!supabase || !userId || !datasetId) return false
  try {
    const { error: jobError } = await supabase.from('cleaning_jobs').insert({
      dataset_id: datasetId,
      user_id: userId,
      rules,
      problems_detected: result.problemas,
      problems_fixed: result.correcciones,
      rows_before: result.resumen.filas_antes,
      rows_after: result.resumen.filas_despues,
      quality_before: result.resumen.calidad_antes,
      quality_after: result.resumen.calidad_despues,
      status: 'completado',
    })
    if (jobError) {
      console.warn('[persistencia] Falló el insert en cleaning_jobs:', jobError.message)
      return false
    }
    const { error: dsError } = await supabase
      .from('datasets')
      .update({
        status: 'limpio',
        quality: result.resumen.calidad_despues,
        rows: result.resumen.filas_despues,
        columns: result.resumen.columnas_despues,
      })
      .eq('id', datasetId)
    if (dsError) {
      console.warn('[persistencia] Falló el update de datasets:', dsError.message)
      return false
    }
    try {
      await logActivity('limpieza', `Limpieza de datos completada: ${result.archivo}`, datasetId)
    } catch (err) {
      console.warn('[persistencia] No se pudo registrar actividad de limpieza:', err)
    }
    return true
  } catch (err) {
    console.warn('[persistencia] Error de red guardando la limpieza:', err)
    return false
  }
}

/** Fase 7 §5.10: persiste el mapeo de roles corregido por el usuario en
 * dataset_columns (requiere la migración 0008: policy + grant de update).
 * Best-effort: la corrección aplica igual en la sesión aunque esto falle. */
export async function saveColumnMapping(
  datasetId: string | null,
  mapping: Record<string, string>,
): Promise<boolean> {
  if (!supabase || !datasetId) return false
  try {
    // Limpiar roles anteriores y asignar los nuevos, columna por columna.
    const { error: clearError } = await supabase
      .from('dataset_columns')
      .update({ mapped_role: null })
      .eq('dataset_id', datasetId)
    if (clearError) {
      console.warn('[persistencia] No se pudo limpiar el mapeo previo:', clearError.message)
      return false
    }
    for (const [role, column] of Object.entries(mapping)) {
      if (!column) continue
      const { error } = await supabase
        .from('dataset_columns')
        .update({ mapped_role: role })
        .eq('dataset_id', datasetId)
        .eq('original_name', column)
      if (error) {
        console.warn(`[persistencia] No se pudo guardar el rol ${role}:`, error.message)
        return false
      }
    }
    return true
  } catch (err) {
    console.warn('[persistencia] Error de red guardando el mapeo:', err)
    return false
  }
}

/** Guarda un análisis de Explorar datos (migración 0004). Best-effort. */export async function saveAnalysis(
  datasetId: string | null,
  name: string,
  config: Record<string, unknown>,
  findings: string[],
  recommendation: Record<string, unknown> | null,
): Promise<boolean> {
  const userId = await getUserId()
  if (!supabase || !userId) return false
  const { error } = await supabase.from('analyses').insert({
    user_id: userId,
    dataset_id: datasetId,
    name,
    config,
    findings,
    recommendation,
  })
  if (!error) {
    try { await logActivity('analisis', `Análisis guardado: ${name}`, datasetId) } catch { /* best-effort */ }
  }
  return !error
}

export async function logActivity(
  type: 'carga' | 'estandarizacion' | 'limpieza' | 'analisis' | 'chat' | 'recomendacion',
  description: string,
  datasetId: string | null = null,
): Promise<boolean> {
  const userId = await getUserId()
  if (!supabase || !userId) return false
  const { error } = await supabase.from('activity_log').insert({
    user_id: userId,
    dataset_id: datasetId,
    activity_type: type,
    description,
  })
  if (error) {
    console.warn('[persistencia] Fallo el insert en activity_log:', error.message)
    return false
  }
  return true
}
