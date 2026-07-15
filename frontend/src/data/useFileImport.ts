/** Flujo compartido de importación de archivos (Estandarización y Conectores).
 *
 * Sube a Storage + inserta en datasets (best-effort), actualiza el contexto y
 * ejecuta /standardize. Devuelve true si el archivo quedó estandarizado.
 */

import { useState } from 'react'
import { ApiError, apiPost, apiPostJson, buildDatasetForm } from '../lib/api'
import {
  insertDataset,
  markStandardized,
  uploadToStorage,
  type DatasetSource,
} from '../lib/datasets'
import { PLAN_ENFORCEMENT, normalizePlan } from '../lib/plans'
import { usePlan } from '../lib/usePlan'
import { supabaseConfigured } from '../lib/supabase'
import type { StandardizeResult } from '../lib/types'
import { useDataset } from './DatasetContext'

export function useFileImport() {
  const { setUploaded, setStandardization } = useDataset()
  const { plan, isAdmin } = usePlan()
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [persistWarning, setPersistWarning] = useState<string | null>(null)
  // Fase 13: cuentas sin plan — cada intento de subir abre el panel de planes.
  const [planBlocked, setPlanBlocked] = useState(false)

  const importFile = async (
    selected: File,
    options: { source?: DatasetSource } = {},
  ): Promise<boolean> => {
    setError(null)
    setPersistWarning(null)
    if (PLAN_ENFORCEMENT && !isAdmin && normalizePlan(plan) === 'sin_plan') {
      setPlanBlocked(true)
      return false
    }
    if (!/\.(csv|xlsx)$/i.test(selected.name)) {
      setError('Formato no soportado. Sube un Excel moderno (.xlsx) o CSV (.csv); si tienes un .xls antiguo, guárdalo como .xlsx primero.')
      return false
    }
    setImporting(true)
    try {
      // Persistencia best-effort: Storage + fila en datasets (si hay Supabase)
      const storagePath = await uploadToStorage(selected)
      const datasetId = await insertDataset(selected, storagePath, options.source ?? 'excel_csv')
      if (supabaseConfigured && (!storagePath || !datasetId)) {
        // No bloquea el pipeline, pero el usuario debe saber que no quedó guardado
        setPersistWarning(
          'Tu archivo se procesará igual, pero no se pudo guardar en el historial ' +
            '(revisa el bucket y las políticas RLS en Supabase).',
        )
      }
      setUploaded(selected, datasetId, storagePath)

      // Fase 8: retención de Storage (fire-and-forget). Poda archivos viejos
      // según el plan del usuario; jamás bloquea ni rompe la carga.
      if (storagePath) {
        void apiPostJson('/storage/retention', {}).catch(() => undefined)
      }

      const result = await apiPost<StandardizeResult>(
        '/standardize',
        buildDatasetForm(selected, storagePath),
      )
      setStandardization(result)
      const marked = await markStandardized(datasetId, result)
      if (!marked && supabaseConfigured && datasetId) {
        setPersistWarning(
          'El archivo se estandarizó correctamente, pero no se pudo guardar todo el detalle en el historial.',
        )
      }
      return true
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ocurrió un error al estandarizar.')
      return false
    } finally {
      setImporting(false)
    }
  }

  return {
    importing,
    error,
    persistWarning,
    importFile,
    setError,
    planBlocked,
    dismissPlanBlocked: () => setPlanBlocked(false),
  }
}
