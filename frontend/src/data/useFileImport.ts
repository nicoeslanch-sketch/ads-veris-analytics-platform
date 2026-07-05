/** Flujo compartido de importación de archivos (Estandarización y Conectores).
 *
 * Sube a Storage + inserta en datasets (best-effort), actualiza el contexto y
 * ejecuta /standardize. Devuelve true si el archivo quedó estandarizado.
 */

import { useState } from 'react'
import { ApiError, apiPost, buildDatasetForm } from '../lib/api'
import { insertDataset, markStandardized, uploadToStorage } from '../lib/datasets'
import { supabaseConfigured } from '../lib/supabase'
import type { StandardizeResult } from '../lib/types'
import { useDataset } from './DatasetContext'

export function useFileImport() {
  const { setUploaded, setStandardization } = useDataset()
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [persistWarning, setPersistWarning] = useState<string | null>(null)

  const importFile = async (selected: File): Promise<boolean> => {
    setError(null)
    setPersistWarning(null)
    if (!/\.(csv|xlsx|xls)$/i.test(selected.name)) {
      setError('Formato no soportado. Sube un archivo Excel (.xlsx) o CSV (.csv).')
      return false
    }
    setImporting(true)
    try {
      // Persistencia best-effort: Storage + fila en datasets (si hay Supabase)
      const storagePath = await uploadToStorage(selected)
      const datasetId = await insertDataset(selected, storagePath)
      if (supabaseConfigured && (!storagePath || !datasetId)) {
        // No bloquea el pipeline, pero el usuario debe saber que no quedó guardado
        setPersistWarning(
          'Tu archivo se procesará igual, pero no se pudo guardar en el historial ' +
            '(revisa el bucket y las políticas RLS en Supabase).',
        )
      }
      setUploaded(selected, datasetId, storagePath)

      const result = await apiPost<StandardizeResult>(
        '/standardize',
        buildDatasetForm(selected, storagePath),
      )
      setStandardization(result)
      await markStandardized(datasetId, result)
      return true
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ocurrió un error al estandarizar.')
      return false
    } finally {
      setImporting(false)
    }
  }

  return { importing, error, persistWarning, importFile, setError }
}
