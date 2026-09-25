/** Flujo compartido de importación de archivos (Estandarización y Conectores).
 *
 * Sube a Storage + inserta en datasets (best-effort), actualiza el contexto y
 * ejecuta /standardize/jobs. Devuelve true si el archivo quedó estandarizado.
 */

import { useEffect, useRef, useState } from 'react'
import { ApiError, apiPostJob, apiPostJson, buildDatasetForm, type AnalysisJobResponse } from '../lib/api'
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
  const { setUploaded, setUploadPersistence, setStandardization } = useDataset()
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
  const [importProgress, setImportProgress] = useState<AnalysisJobResponse<StandardizeResult> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [persistWarning, setPersistWarning] = useState<string | null>(null)
  // Fase 13: cuentas sin acceso — cada intento de subir abre el panel comercial.
  const [planBlocked, setPlanBlocked] = useState(false)
  const importSequenceRef = useRef(0)
  const importAbortRef = useRef<AbortController | null>(null)

  useEffect(() => () => importAbortRef.current?.abort(), [])

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
    options: { source?: DatasetSource; connectorSourceId?: string | null } = {},
  ): Promise<boolean> => {
    setError(null)
    setPersistWarning(null)
    setImportProgress(null)
    if (!/\.(csv|xlsx)$/i.test(selected.name)) {
      setError('Formato no soportado. Sube un Excel moderno (.xlsx) o CSV (.csv); si tienes un .xls antiguo, guárdalo como .xlsx primero.')
      return false
    }
    importAbortRef.current?.abort()
    const controller = new AbortController()
    importAbortRef.current = controller
    const sequence = ++importSequenceRef.current
    const isCurrent = () => (
      importSequenceRef.current === sequence && !controller.signal.aborted
    )
    setImporting(true)
    try {
      if (!(await waitForUploadAccess())) return false
      if (!isCurrent()) return false
      // El archivo elegido pasa a ser autoritativo antes de Storage/API. Esto
      // cancela una restauración pendiente y evita que el documento anterior
      // reaparezca mientras el nuevo termina de subirse.
      demo.exit()
      setUploaded(selected, null, null)
      // Persistencia best-effort: Storage + fila en datasets (si hay Supabase)
      let storagePath: string | null = null
      try {
        storagePath = await uploadToStorage(selected, controller.signal)
      } catch (uploadError) {
        if (uploadError instanceof ApiError && uploadError.status === 507) throw uploadError
        if (!isCurrent()) return false
        setPersistWarning((uploadError instanceof Error ? uploadError.message : 'No se pudo guardar el archivo.') + ' El análisis seguirá en esta sesión, sin persistencia del archivo.')
      }
      if (!isCurrent()) return false
      const datasetId = await insertDataset(selected, storagePath, options.source ?? 'excel_csv')
      if (!isCurrent()) return false
      if (supabaseConfigured && (!storagePath || !datasetId)) {
        // No bloquea el pipeline, pero el usuario debe saber que no quedó guardado
        setPersistWarning((previous) => previous ?? (
          'Tu archivo se procesará igual, pero no se pudo guardar en el historial ' +
            'para retomarlo después.'
        ))
      }
      if (!setUploadPersistence(selected, datasetId, storagePath)) return false

      // Fase 8: retención de Storage (fire-and-forget). Poda archivos viejos
      // según el plan del usuario; jamás bloquea ni rompe la carga.
      if (storagePath) {
        void apiPostJson('/storage/retention', {}).catch(() => undefined)
      }

      const result = await apiPostJob<StandardizeResult>(
        '/standardize/jobs',
        buildDatasetForm(selected, storagePath, {
          ...(datasetId ? { dataset_id: datasetId } : {}),
        }),
        {
          signal: controller.signal,
          timeoutMs: 15 * 60_000,
          onProgress: (job) => { if (isCurrent()) setImportProgress(job) },
        },
      )
      if (!isCurrent()) return false
      if (!setStandardization(result, { expectedFile: selected })) return false
      if (options.connectorSourceId) {
        void apiPostJson(`/connectors/sheets/sources/${options.connectorSourceId}/link`, {
          dataset_id: datasetId,
        }).catch(() => undefined)
      }
      // History persistence is best-effort and must not extend the processing
      // spinner after the usable result has already arrived.
      void markStandardized(datasetId, result).then((marked) => {
        if (isCurrent() && !marked && supabaseConfigured && datasetId) {
          setPersistWarning(
            'El archivo se estandarizó correctamente, pero no se pudo guardar todo el detalle en el historial.',
          )
        }
      })
      return true
    } catch (err) {
      if (isCurrent()) {
        setError(err instanceof ApiError ? err.message : 'Ocurrió un error al estandarizar.')
      }
      return false
    } finally {
      if (importSequenceRef.current === sequence) {
        setImporting(false)
        if (importAbortRef.current === controller) importAbortRef.current = null
      }
    }
  }

  return {
    importing,
    importStatus: importProgress?.status === 'queued'
      ? 'En cola: esperando un turno de procesamiento...'
      : importProgress?.phase === 'saving'
        ? 'Guardando la estandarización...'
        : importProgress ? 'Estandarizando tus datos...' : 'Preparando el archivo...',
    cancelImport: () => {
      importAbortRef.current?.abort()
      setError('Importación cancelada.')
    },
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
