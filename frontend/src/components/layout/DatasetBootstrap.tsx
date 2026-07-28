/** Fast, best-effort restoration of the user's latest dataset.
 *
 * The backend returns a small, versioned snapshot in one request. It only
 * rebuilds the pipeline with pandas when the snapshot is missing or stale.
 */

import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { useDataset } from '../../data/DatasetContext'
import { ApiError, apiPost, apiPostJson } from '../../lib/api'
import { useAccess } from '../../lib/access'
import {
  restoredAnalysisSelection,
  restoredSheetStatus,
  withPublicAnalysisScope,
} from '../../lib/multiSheet'
import { supabaseConfigured } from '../../lib/supabase'
import type { RestoreLatestResult } from '../../lib/types'

const attemptedUsers = new Set<string>()
const AUTO_RESTORE_TIMEOUT_MS = 90_000

export default function DatasetBootstrap() {
  const { user } = useAuth()
  const { status: accessStatus, can } = useAccess()
  const {
    file,
    datasetId,
    datasetRevision,
    analysisScope,
    metricsStale,
    restoreDataset,
    setMetrics,
    setRestoring: setContextRestoring,
  } = useDataset()
  const [restoring, setRestoring] = useState<string | null>(null)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const [refreshingMetrics, setRefreshingMetrics] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [refreshRetry, setRefreshRetry] = useState(0)
  const cancelledRef = useRef(false)
  const restoreAbortRef = useRef<AbortController | null>(null)
  const refreshAttemptRef = useRef<string | null>(null)

  // Fase 13: al cerrar sesión se limpia el intento — reingresar con la
  // misma cuenta vuelve a restaurar el último trabajo.
  useEffect(() => {
    if (!user) attemptedUsers.clear()
  }, [user])

  useEffect(() => {
    if (!supabaseConfigured || !user) return
    if (file || attemptedUsers.has(user.id)) return
    // Fase 14: sin acceso resuelto no se dispara nada; sin capacidad de
    // dashboard (sin plan / prueba expirada) no hay trabajo que restaurar —
    // el backend igual respondería 403 en /restore/latest.
    if (accessStatus === 'loading') return
    if (accessStatus === 'resolved' && !can('view_dashboard')) {
      attemptedUsers.add(user.id)
      return
    }
    cancelledRef.current = false
    let active = true
    const controller = new AbortController()
    restoreAbortRef.current = controller
    const restoreRevision = datasetRevision
    let restoredAvailable = false

    const applyRestored = (restored: RestoreLatestResult) => {
      if (!restored.dataset || !restored.standardization) return false
      const placeholder = new File([], restored.dataset.name, {
        type: 'application/octet-stream',
      })
      const restoredSessions = Object.fromEntries(
        Object.entries(restored.sheet_sessions ?? {}).map(([name, session]) => {
          const restoredError = restored.sheet_errors?.[name] ?? null
          return [
            name,
            {
              standardization: session.standardization,
              cleaning: session.cleaning,
              mappingOverride: session.mapping,
              eliminarDuplicados: session.eliminar_duplicados,
              status: restoredSheetStatus(restoredError, Boolean(session.cleaning)),
              error: restoredError,
            },
          ]
        }),
      )
      const restoredSelection = restoredAnalysisSelection(
        restored.analysis_scope,
        restored.selection_mode,
      )
      const restoredMetrics = restored.metrics
        ? withPublicAnalysisScope(restored.metrics)
        : null
      return restoreDataset(
        placeholder,
        restored.dataset.id,
        restored.dataset.storage_path,
        restored.standardization,
        restored.cleaning ?? null,
        restoredMetrics,
        restored.mapping ?? null,
        Boolean(restored.eliminar_duplicados),
        {
          activeSheet: restored.active_sheet ?? null,
          availableSheets:
            restored.available_sheets ?? restored.standardization.carga?.hojas_disponibles ?? [],
          combineSheets: Boolean(restored.combine_sheets),
          sheetSessions: restoredSessions,
          selectedSheets: restored.selected_sheets,
          sheetErrors: restored.sheet_errors,
          analysisScope: restoredSelection.analysisScope,
          selectionMode: restoredSelection.selectionMode,
          expectedRevision: restoreRevision,
          metricsStale: Boolean(restored.metrics_stale),
        },
      )
    }

    const run = async () => {
      setRestoring('documento reciente')
      setContextRestoring(true)
      setRestoreError(null)
      try {
        const restored = await apiPostJson<RestoreLatestResult>(
          '/restore/latest',
          {},
          { timeoutMs: AUTO_RESTORE_TIMEOUT_MS, signal: controller.signal },
        )
        if (!active || cancelledRef.current) return
        restoredAvailable = applyRestored(restored)
        if (!restoredAvailable) return
        // Las páginas visibles recalculan sus indicadores con el motor actual.
        // No reconstruimos aquí todo el libro: hacerlo en paralelo con
        // métricas o relaciones duplicaba el trabajo y podía cancelar la
        // primera carga de un documento restaurado.
      } catch (err) {
        if (active && !cancelledRef.current) {
          // Un 403 significa "sin acceso de procesamiento" (cuenta sin plan o
          // prueba expirada): no hay nada que restaurar y no es un error.
          if (!(err instanceof ApiError && err.status === 403)) {
            setRestoreError(
              err instanceof ApiError
                  ? `No pudimos restaurar automáticamente tu último trabajo. ${err.message}`
                  : 'No pudimos restaurar automáticamente tu último trabajo.',
            )
          }
        }
      } finally {
        if (active) {
          attemptedUsers.add(user.id)
          setRestoring(null)
          setContextRestoring(false)
          // Retention stays off the critical path of the visible restoration.
          void apiPostJson('/storage/retention', {}).catch(() => undefined)
        }
      }
    }
    void run()
    return () => {
      active = false
      controller.abort()
      attemptedUsers.add(user.id)
      if (restoreAbortRef.current === controller) restoreAbortRef.current = null
      setRestoring(null)
      setContextRestoring(false)
    }
  }, [user, file, datasetRevision, restoreDataset, accessStatus, can, setContextRestoring])

  // Un snapshot de otro motor o de un modelo derivado anterior se muestra
  // inmediatamente y se actualiza una sola vez en segundo plano.
  // /restore/refresh reutiliza la limpieza guardada, reserva una revisión
  // atómica y persiste el resultado nuevo; así la próxima recarga no vuelve a
  // ejecutar /metrics ni repite actividad de limpieza.
  useEffect(() => {
    if (
      !user
      || !datasetId
      || !metricsStale
      || restoring
    ) return
    const attemptKey = `${datasetId}:${refreshRetry}`
    if (refreshAttemptRef.current === attemptKey) return
    refreshAttemptRef.current = attemptKey
    const controller = new AbortController()
    let active = true
    const run = async () => {
      setRefreshingMetrics(true)
      setRefreshError(null)
      try {
        const form = new FormData()
        form.append('dataset_id', datasetId)
        const refreshed = await apiPost<RestoreLatestResult>(
          '/restore/refresh',
          form,
          { timeoutMs: 300_000, signal: controller.signal },
        )
        if (!active || controller.signal.aborted || !refreshed.metrics) return
        setMetrics(withPublicAnalysisScope(refreshed.metrics))
      } catch (err) {
        if (!active || controller.signal.aborted) return
        setRefreshError(
          err instanceof ApiError
            ? `No pudimos actualizar los indicadores guardados. ${err.message}`
            : 'No pudimos actualizar los indicadores guardados.',
        )
      } finally {
        if (active) setRefreshingMetrics(false)
      }
    }
    void run()
    return () => {
      active = false
      controller.abort()
    }
  }, [analysisScope?.mode, datasetId, metricsStale, refreshRetry, restoring, setMetrics, user])

  if (!restoring && restoreError) {
    return (
      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-gold/35 bg-gold/[0.08] px-4 py-3 text-sm text-navy/80">
        <AlertTriangle className="h-4 w-4 shrink-0 text-gold" />
        <p className="min-w-0 flex-1">
          {restoreError}
        </p>
        <Link
          to="/historial"
          className="shrink-0 rounded-lg border border-navy/20 bg-white px-3 py-1.5 text-xs font-semibold text-navy transition-colors hover:border-teal/60"
        >
          Retomar desde Historial
        </Link>
        <button
          type="button"
          onClick={() => setRestoreError(null)}
          className="shrink-0 rounded-lg px-2 py-1.5 text-xs font-semibold text-navy/55 transition-colors hover:bg-white/70 hover:text-navy"
        >
          Ocultar
        </button>
      </div>
    )
  }

  if (!restoring && (refreshingMetrics || refreshError)) {
    return (
      <div className={`mb-5 flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 text-sm text-navy/80 ${
        refreshError
          ? 'border-gold/35 bg-gold/[0.08]'
          : 'border-teal/25 bg-teal/[0.06]'
      }`}>
        {refreshError
          ? <AlertTriangle className="h-4 w-4 shrink-0 text-gold" />
          : <Loader2 className="h-4 w-4 shrink-0 animate-spin text-teal" />}
        <p className="min-w-0 flex-1">
          {refreshError ?? (
            <>
              Ya puedes usar el resultado guardado. Estamos actualizando sus indicadores
              una sola vez con el motor actual para que las próximas recargas sean inmediatas.
            </>
          )}
        </p>
        {refreshError && (
          <button
            type="button"
            onClick={() => {
              refreshAttemptRef.current = null
              setRefreshRetry((value) => value + 1)
            }}
            className="shrink-0 rounded-lg border border-navy/20 bg-white px-3 py-1.5 text-xs font-semibold text-navy transition-colors hover:border-teal/60"
          >
            Reintentar actualización
          </button>
        )}
      </div>
    )
  }

  if (!restoring) return null
  return (
    <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-teal/25 bg-teal/[0.06] px-4 py-3 text-sm text-navy/80">
      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-teal" />
      <p className="min-w-0 flex-1">
        Restaurando tu último trabajo: <strong className="text-navy">{restoring}</strong>…
      </p>
      <Link
        to="/estandarizacion"
        onClick={() => {
          cancelledRef.current = true
          restoreAbortRef.current?.abort()
          setRestoring(null)
          setContextRestoring(false)
        }}
        className="shrink-0 rounded-lg border border-navy/20 bg-white px-3 py-1.5 text-xs font-semibold text-navy transition-colors hover:border-teal/60"
      >
        Empezar con otro documento
      </Link>
    </div>
  )
}
