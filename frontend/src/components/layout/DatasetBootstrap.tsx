/** Restaura el último trabajo del usuario al iniciar sesión (Fase 11 §6).
 *
 * Al entrar con la sesión vacía, se busca el dataset más reciente del
 * Historial y se rehidrata el pipeline usando storage_path (el archivo NO se
 * descarga al navegador: el backend lo lee directo de Storage y el resto de
 * módulos sale del caché del servidor). Es una cortesía best-effort:
 * cualquier fallo se silencia y el usuario siempre puede partir de cero con
 * "Empezar con otro documento".
 */

import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { useDataset } from '../../data/DatasetContext'
import { ApiError, apiPost, apiPostJson, buildDatasetForm } from '../../lib/api'
import { fetchDatasets, fetchLatestCleaningRules } from '../../lib/history'
import { supabaseConfigured } from '../../lib/supabase'
import { DEFAULT_RULES, type CleanResult, type StandardizeResult } from '../../lib/types'

// Un intento por usuario por sesión del navegador (no por navegación).
const attemptedUsers = new Set<string>()
const AUTO_RESTORE_TIMEOUT_MS = 90_000

export default function DatasetBootstrap() {
  const { user } = useAuth()
  const { file, setUploaded, setStandardization, setCleaning } = useDataset()
  const [restoring, setRestoring] = useState<string | null>(null)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const cancelledRef = useRef(false)
  const restoreAbortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!supabaseConfigured || !user) return
    if (file || attemptedUsers.has(user.id)) return
    cancelledRef.current = false
    let active = true
    const controller = new AbortController()
    restoreAbortRef.current = controller

    // La retención de Storage también corre al iniciar sesión (Fase 11 §6.3):
    // los archivos antiguos se podan aunque el usuario no cargue nada nuevo.
    void apiPostJson('/storage/retention', {}).catch(() => undefined)

    const run = async () => {
      const datasets = await fetchDatasets(10)
      if (!active || cancelledRef.current) return
      if (!Array.isArray(datasets)) {
        attemptedUsers.add(user.id)
        return
      }
      const latest = datasets.find((d) => d.storage_path && d.status !== 'error')
      if (!latest?.storage_path) {
        attemptedUsers.add(user.id)
        return
      }
      setRestoring(latest.name)
      setRestoreError(null)
      try {
        // Placeholder sin bytes: solo aporta el nombre; la data viaja por storage_path.
        const placeholder = new File([], latest.name, { type: 'application/octet-stream' })
        const std = await apiPost<StandardizeResult>(
          '/standardize',
          buildDatasetForm(placeholder, latest.storage_path),
          { timeoutMs: AUTO_RESTORE_TIMEOUT_MS, signal: controller.signal },
        )
        if (!active || cancelledRef.current) return
        let cleaned: CleanResult | null = null
        if (latest.status === 'limpio') {
          const rules = await fetchLatestCleaningRules(latest.id)
          cleaned = await apiPost<CleanResult>(
            '/clean',
            buildDatasetForm(placeholder, latest.storage_path, {
              apply: 'true',
              rules: JSON.stringify(rules ?? DEFAULT_RULES),
            }),
            { timeoutMs: AUTO_RESTORE_TIMEOUT_MS, signal: controller.signal },
          )
          if (!active || cancelledRef.current) return
        }
        // El contexto se toca UNA sola vez, al final: jamás queda a medias.
        setUploaded(placeholder, latest.id, latest.storage_path)
        setStandardization(std)
        if (cleaned) setCleaning(cleaned)
      } catch (err) {
        if (active && !cancelledRef.current) {
          setRestoreError(
            err instanceof ApiError
              ? err.message
              : 'No pudimos restaurar automaticamente tu ultimo trabajo.',
          )
        }
      } finally {
        if (active) {
          attemptedUsers.add(user.id)
          setRestoring(null)
        }
      }
    }
    void run()
    return () => {
      active = false
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, file])

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
        }}
        className="shrink-0 rounded-lg border border-navy/20 bg-white px-3 py-1.5 text-xs font-semibold text-navy transition-colors hover:border-teal/60"
      >
        Empezar con otro documento
      </Link>
    </div>
  )
}
