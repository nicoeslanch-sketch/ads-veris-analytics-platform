import { supabase } from './supabase'
import type { CleanResult, CleaningRules, StandardizeResult } from './types'

const STORAGE_BUCKET = 'datasets'

export async function uploadToStorage(file: File): Promise<string | null> {
  if (!supabase) return null

  const { data: userData } = await supabase.auth.getUser()
  const userId = userData.user?.id
  if (!userId) return null

  const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_')
  const storagePath = `${userId}/${crypto.randomUUID()}-${safeName}`
  const { error } = await supabase.storage.from(STORAGE_BUCKET).upload(storagePath, file, {
    upsert: false,
  })
  if (error) return null
  return storagePath
}

export async function insertDataset(file: File, storagePath: string | null): Promise<string | null> {
  if (!supabase) return null

  const { data: userData } = await supabase.auth.getUser()
  const userId = userData.user?.id
  if (!userId) return null

  const { data, error } = await supabase
    .from('datasets')
    .insert({
      user_id: userId,
      name: file.name,
      storage_path: storagePath,
      source: 'excel_csv',
      status: 'cargado',
    })
    .select('id')
    .single()

  if (error) return null
  return data.id as string
}

export async function markStandardized(
  datasetId: string | null,
  result: StandardizeResult,
): Promise<void> {
  if (!supabase || !datasetId) return

  await supabase
    .from('datasets')
    .update({
      rows: result.filas,
      columns: result.columnas,
      status: 'estandarizado',
    })
    .eq('id', datasetId)
}

export async function saveCleaningJob(
  datasetId: string | null,
  rules: CleaningRules,
  result: CleanResult,
): Promise<void> {
  if (!supabase || !datasetId) return

  const { data: userData } = await supabase.auth.getUser()
  const userId = userData.user?.id
  if (!userId) return

  await supabase.from('cleaning_jobs').insert({
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

  await supabase
    .from('datasets')
    .update({
      rows: result.resumen.filas_despues,
      columns: result.resumen.columnas_despues,
      quality: result.resumen.calidad_despues,
      status: 'limpio',
    })
    .eq('id', datasetId)
}
