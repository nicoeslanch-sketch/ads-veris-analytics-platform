/** Flujo compartido de importación de archivos (Estandarización y Conectores).
 *
 * Sube a Storage + inserta en datasets (best-effort), actualiza el contexto y
 * ejecuta /standardize. Devuelve true si el archivo quedó estandarizado.
 */

import { useRef, useState } from 'react'
import { ApiError, apiPost, apiPostJson, buildDatasetForm } from '../lib/api'
import {
  insertDataset,
  markStandardized,
  uploadToStorage,
  type DatasetSource,
} from '../lib/datasets'
import { useAccess } from '../lib/access'
import { supabaseConfigured } from '../lib/supabase'
import type { StandardizeResult } from '../lib/types'
import { useDataset } from './DatasetContext'
import { useDemo } from '../demo/DemoContext'

export function useFileImport() {
  const { setUploaded, setStandardization } = useDataset()
  // Bug: subir un archivo real mientras se ve la demo ficticia dejaba el
  // banner y los números de "Comercial Andes SpA" activos hasta que el
  // usuario salía manualmente — confundía datos ficticios con reales.
  const demo = useDemo()
  // Fase 14: la puerta lee el AccessContext ÚNICO (capacidades del servidor,
  // trial incluido). Sin acceso optimista: mientras carga, no se sube nada.
  const { status: accessStatus, can, refresh: refreshAccess } = useAccess()
  const accessRef = useRef({ status: accessStatus, can })
  accessRef.current = { status: accessStatus, can }
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [persistWarning, setPersistWarning] = useState<string | null>(null)
  // Fase 13: cuentas sin acceso — cada intento de subir abre el panel comercial.
  const [planBlocked, setPlanBlocked] = useState(false)

  /** Puerta previa a CUALQUIER byte o llamada: las páginas la consultan antes
   * de abrir el selector de archivos, leer un drop o llamar a la API
   * (Conectores/Sheets). `importFile` la vuelve a aplicar por defensa en
   * profundidad. Regla: ningún byte sale del navegador y ninguna llamada de
   * procesamiento comienza sin el contexto de acceso resuelto y aprobado. */
  const checkUploadAllowed = (): boolean => {
    const current = accessRef.current
    if (current.status === 'loading') return false
    if (current.status === 'error') {
      setError('No se pudo verificar tu acceso. Revisa tu conexión e intenta nuevamente.')
      refreshAccess()
      return false
    }
    if (!current.can('standardize')) {
      setPlanBlocked(true)
      return false
    }
    return true
  }

  /** El selector nativo provoca blur/focus y AccessProvider revalida el plan.
   * Conservamos el archivo elegido y esperamos la respuesta autoritativa antes
   * de leer/subir bytes, en vez de obligar al usuario a seleccionarlo de nuevo. */
  const waitForUploadAccess = async (): Promise<boolean> => {
    const deadline = Date.now() + 10_000
    while (accessRef.current.status === 'loading' && Date.now() < deadline) {
      await new Promise((resolve) => window.setTimeout(resolve, 50))
    }
    if (accessRef.current.status === 'loading') {
      setError('La verificación de acceso está tardando demasiado. Intenta nuevamente.')
      return false
    }
    return checkUploadAllowed()
  }

  const importFile = async (
    selected: File,
    options: { source?: DatasetSource } = {},
  ): Promise<boolean> => {
    setError(null)
    setPersistWarning(null)
    if (!/\.(csv|xlsx)$/i.test(selected.name)) {
      setError('Formato no soportado. Sube un Excel moderno (.xlsx) o CSV (.csv); si tienes un .xls antiguo, guárdalo como .xlsx primero.')
      return false
    }
    setImporting(true)
    try {
      if (!(await waitForUploadAccess())) return false
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
      demo.exit()
      setUploaded(selected, datasetId, storagePath)

      // Fase 8: retención de Storage (fire-and-forget). Poda archivos viejos
      // según el plan del usuario; jamás bloquea ni rompe la carga.
      if (storagePath) {
        void apiPostJson('/storage/retention', {}).catch(() => undefined)
      }

      const result = await apiPost<StandardizeResult>(
        '/standardize',
        buildDatasetForm(selected, storagePath, {
          ...(datasetId ? { dataset_id: datasetId } : {}),
        }),
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
    checkUploadAllowed,
    accessStatus,
  }
}
