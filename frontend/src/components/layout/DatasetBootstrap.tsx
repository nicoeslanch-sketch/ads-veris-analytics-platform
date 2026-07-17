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
import { ApiError, apiPostJson } from '../../lib/api'
import { useAccess } from '../../lib/access'
import { supabaseConfigured } from '../../lib/supabase'
import type { RestoreLatestResult } from '../../lib/types'

const attemptedUsers = new Set<string>()
const AUTO_RESTORE_TIMEOUT_MS = 90_000

export default function DatasetBootstrap() {
  const { user } = useAuth()
  const { status: accessStatus, can } = useAccess()
  const { file, restoreDataset, setRestoring: setContextRestoring } = useDataset()
  const [restoring, setRestoring] = useState<string | null>(null)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const cancelledRef = useRef(false)
  const restoreAbortRef = useRef<AbortController | null>(null)

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
        if (!restored.dataset || !restored.standardization) return

        const placeholder = new File([], restored.dataset.name, {
          type: 'application/octet-stream',
        })
        const restoredSessions = Object.fromEntries(
          Object.entries(restored.sheet_sessions ?? {}).map(([name, session]) => [
            name,
            {
              standardization: session.standardization,
              cleaning: session.cleaning,
              mappingOverride: session.mapping,
              eliminarDuplicados: session.eliminar_duplicados,
            },
          ]),
        )
        restoreDataset(
          placeholder,
          restored.dataset.id,
          restored.dataset.storage_path,
          restored.standardization,
          restored.cleaning ?? null,
          restored.metrics ?? null,
          restored.mapping ?? null,
          Boolean(restored.eliminar_duplicados),
          {
            activeSheet: restored.active_sheet ?? null,
            availableSheets:
              restored.available_sheets ?? restored.standardization.carga?.hojas_disponibles ?? [],
            combineSheets: Boolean(restored.combine_sheets),
            sheetSessions: restoredSessions,
          },
        )
      } catch (err) {
        if (active && !cancelledRef.current) {
          // Un 403 significa "sin acceso de procesamiento" (cuenta sin plan o
          // prueba expirada): no hay nada que restaurar y no es un error.
          if (!(err instanceof ApiError && err.status === 403)) {
            setRestoreError(
              err instanceof ApiError
                ? err.message
                : 'No pudimos restaurar automaticamente tu ultimo trabajo.',
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
    }
  }, [user, file, restoreDataset, accessStatus, can, setContextRestoring])

  if (!restoring && restoreError) {
    return (
      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-gold/35 bg-gold/[0.08] px-4 py-3 text-sm text-navy/80">
        <AlertTriangle className="h-4 w-4 shrink-0 text-gold" />
        <p className="min-w-0 flex-1">
          No se pudo restaurar automaticamente el ultimo trabajo. {restoreError}
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
