/**
 * Historial (SPEC §7 — Fase 5, MVP).
 *
 * Trazabilidad de la cuenta: archivos cargados (con estado, calidad y
 * "Retomar" para rehidratar la sesión desde Supabase Storage) + actividad
 * completa (cargas, estandarizaciones, limpiezas, análisis, chat).
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  CheckCircle2,
  Eraser,
  FileSpreadsheet,
  History,
  Lightbulb,
  Loader2,
  MessageCircle,
  RotateCcw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  type LucideIcon,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import EmptyState from '../components/ui/EmptyState'
import { useDataset } from '../data/DatasetContext'
import { useDemo } from '../demo/DemoContext'
import { apiDelete, apiPost, buildDatasetForm, ApiError } from '../lib/api'
import {
  deleteAnalysis,
  fetchActivity,
  fetchAnalyses,
  fetchDatasets,
  fetchLatestCleaningConfig,
  hasVerifiedMonetaryIntegrity,
  sanitizeActivityDescription,
  type ActivityRow,
  type ActivityType,
  type AnalysisRow,
  type DatasetRow,
} from '../lib/history'
import { supabaseConfigured } from '../lib/supabase'
import { formatDateTime, formatNumber, formatRelativeTime } from '../lib/format'
import { DEFAULT_RULES, type CleanResult, type StandardizeResult } from '../lib/types'

const ACTIVITY_META: Record<ActivityType, { label: string; icon: LucideIcon; tone: string }> = {
  carga: { label: 'Carga', icon: Upload, tone: 'bg-teal/10 text-teal' },
  estandarizacion: { label: 'Estandarización', icon: Sparkles, tone: 'bg-gold/15 text-gold' },
  limpieza: { label: 'Limpieza', icon: Eraser, tone: 'bg-green/10 text-green' },
  analisis: { label: 'Análisis', icon: Search, tone: 'bg-navy/10 text-navy' },
  chat: { label: 'Chat IA', icon: MessageCircle, tone: 'bg-teal/10 text-teal' },
  recomendacion: { label: 'Recomendación', icon: Lightbulb, tone: 'bg-gold/15 text-gold' },
  eliminacion: { label: 'Eliminación', icon: Trash2, tone: 'bg-coral/10 text-coral' },
}

const STATUS_BADGE: Record<DatasetRow['status'], { label: string; tone: 'teal' | 'gold' | 'green' | 'coral' }> = {
  cargado: { label: 'Cargado', tone: 'teal' },
  estandarizado: { label: 'Estandarizado', tone: 'gold' },
  limpio: { label: 'Limpio', tone: 'green' },
  error: { label: 'Error', tone: 'coral' },
}

const SOURCE_BADGE: Record<string, { label: string; tone: 'teal' | 'green' | 'navy' }> = {
  excel_csv: { label: 'Excel / CSV', tone: 'green' },
  google_sheets: { label: 'Google Sheets', tone: 'teal' },
}

function sourceBadge(source: string | null | undefined) {
  return SOURCE_BADGE[source ?? ''] ?? { label: source || 'Desconocida', tone: 'navy' as const }
}

export default function Historial() {
  const { datasetId, setUploaded, setStandardization, setCleaning, reset } = useDataset()
  // Bug: "Retomar" cambiaba el archivo activo pero dejaba el banner y los
  // números ficticios de la demo visibles hasta salir manualmente.
  const demo = useDemo()
  const navigate = useNavigate()

  const [datasets, setDatasets] = useState<DatasetRow[] | null>(null)
  const [activity, setActivity] = useState<ActivityRow[] | null>(null)
  const [analyses, setAnalyses] = useState<AnalysisRow[] | null>(null)
  const [expandedAnalysis, setExpandedAnalysis] = useState<string | null>(null)
  const [deletingAnalysis, setDeletingAnalysis] = useState<string | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [loading, setLoading] = useState(true)
  const [resuming, setResuming] = useState<string | null>(null)
  const [resumeError, setResumeError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<DatasetRow | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleteNotice, setDeleteNotice] = useState<string | null>(null)
  const cancelDeleteRef = useRef<HTMLButtonElement | null>(null)
  const confirmDeleteRef = useRef<HTMLButtonElement | null>(null)
  const returnFocusRef = useRef<HTMLButtonElement | null>(null)
  const listHeadingRef = useRef<HTMLHeadingElement | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchDatasets(), fetchActivity(), fetchAnalyses()]).then(([ds, act, an]) => {
      if (cancelled) return
      // 'error' ≠ vacío: un fallo de Supabase no debe verse como "sin actividad"
      setLoadError(ds === 'error' || act === 'error' || an === 'error')
      setDatasets(ds === 'error' ? [] : ds)
      setActivity(act === 'error' ? [] : act)
      setAnalyses(an === 'error' ? [] : an)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const handleDeleteAnalysis = async (id: string) => {
    setDeletingAnalysis(id)
    const ok = await deleteAnalysis(id)
    if (ok) setAnalyses((prev) => (prev ?? []).filter((a) => a.id !== id))
    setDeletingAnalysis(null)
  }

  useEffect(() => {
    if (!deleteTarget) return
    cancelDeleteRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !deleting) {
        setDeleteTarget(null)
        requestAnimationFrame(() => returnFocusRef.current?.focus())
      }
      if (event.key === 'Tab') {
        const first = cancelDeleteRef.current
        const last = confirmDeleteRef.current
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last?.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first?.focus()
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [deleteTarget, deleting])

  const closeDeleteDialog = () => {
    if (deleting) return
    setDeleteTarget(null)
    setDeleteError(null)
    requestAnimationFrame(() => returnFocusRef.current?.focus())
  }

  const handleDelete = async () => {
    if (!deleteTarget || deleting) return
    const target = deleteTarget
    setDeleting(true)
    setDeleteError(null)
    setDeleteNotice(null)
    try {
      await apiDelete<{ status: string }>(`/datasets/${target.id}`)
      const [ds, act] = await Promise.all([fetchDatasets(), fetchActivity()])
      setLoadError(ds === 'error' || act === 'error')
      setDatasets(ds === 'error' ? [] : ds)
      setActivity(act === 'error' ? [] : act)
      if (datasetId === target.id) {
        reset()
        setDeleteNotice('Eliminaste el dataset que estabas usando.')
      } else {
        setDeleteNotice(`Se eliminó “${target.name}” y su historial de limpieza.`)
      }
      setDeleteTarget(null)
      requestAnimationFrame(() => listHeadingRef.current?.focus())
    } catch (err) {
      setDeleteError(
        err instanceof ApiError
          ? err.message
          : 'No se pudo completar la eliminación. El trabajo quedó guardado para reintentar.',
      )
    } finally {
      setDeleting(false)
    }
  }

  /** Rehidrata la sesión re-ejecutando el pipeline sobre el archivo de
   * Storage. Fase 11 §5.4: el archivo YA NO se descarga al navegador — todas
   * las llamadas usan storage_path y el backend lo lee directo (con archivos
   * grandes, bajar 15 MB al cliente era la mitad de la lentitud de Retomar);
   * el segundo módulo que lo pida sale del caché del servidor. */
  const handleResume = async (dataset: DatasetRow) => {
    if (!dataset.storage_path) return
    demo.exit()
    setResuming(dataset.id)
    setResumeError(null)
    try {
      // Placeholder liviano: solo aporta el nombre (la data viaja por storage_path).
      const file = new File([], dataset.name, { type: 'application/octet-stream' })
      const result = await apiPost<StandardizeResult>(
        '/standardize',
        buildDatasetForm(file, dataset.storage_path),
      )
      if (dataset.status === 'limpio') {
        // Continuar con las reglas reales del último cleaning_job cuando existan.
        const savedConfig = await fetchLatestCleaningConfig(dataset.id)
        const usedDefaultRules = !savedConfig?.rules
        const cleaned = await apiPost<CleanResult>(
          '/clean',
          buildDatasetForm(file, dataset.storage_path, {
            apply: 'true',
            rules: JSON.stringify(savedConfig?.rules ?? DEFAULT_RULES),
            eliminar_duplicados: String(
              savedConfig?.options.eliminar_duplicados ?? false,
            ),
          }),
        )
        setUploaded(file, dataset.id, dataset.storage_path)
        setStandardization(result)
        setCleaning(cleaned)
        navigate('/', {
          state: usedDefaultRules
            ? {
                resumeWarning:
                  'No encontramos reglas guardadas para este dataset; se retomo con las reglas automaticas por defecto.',
              }
            : undefined,
        })
      } else {
        setUploaded(file, dataset.id, dataset.storage_path)
        setStandardization(result)
        navigate('/limpieza')
      }
    } catch (err) {
      setResumeError(
        err instanceof ApiError ? err.message : 'No se pudo retomar el dataset.',
      )
    } finally {
      setResuming(null)
    }
  }

  if (!supabaseConfigured) {
    return (
      <>
        <PageHeader
          title="Historial"
          subtitle="Revisa todo lo que has hecho en la plataforma: cargas, limpieza, estandarización, análisis y recomendaciones."
        />
        <EmptyState
          icon={History}
          title="El historial requiere Supabase"
          description="En este entorno no hay Supabase configurado, así que la actividad no se persiste. En producción, cada carga, limpieza, análisis y consulta al asistente queda registrada aquí."
        />
      </>
    )
  }

  if (loading) {
    return (
      <>
        <PageHeader title="Historial" subtitle="Cargando tu actividad…" />
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-teal" />
        </div>
      </>
    )
  }

  const hasData =
    (datasets?.length ?? 0) > 0 || (activity?.length ?? 0) > 0 || (analyses?.length ?? 0) > 0

  if (loadError && !hasData) {
    return (
      <>
        <PageHeader
          title="Historial"
          subtitle="Revisa todo lo que has hecho en la plataforma: cargas, limpieza, estandarización, análisis y recomendaciones."
        />
        <Card className="max-w-2xl border-coral/40 bg-coral/5">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-coral" />
            <div>
              <p className="text-sm font-semibold text-navy">No se pudo cargar el historial</p>
              <p className="mt-1 text-xs leading-relaxed text-navy/60">
                Supabase respondió con error (no es que no haya actividad). Revisa que las
                migraciones estén ejecutadas y las políticas RLS activas, y vuelve a intentar.
              </p>
            </div>
          </div>
        </Card>
      </>
    )
  }

  if (!hasData) {
    return (
      <>
        <PageHeader
          title="Historial"
          subtitle="Revisa todo lo que has hecho en la plataforma: cargas, limpieza, estandarización, análisis y recomendaciones."
        />
        <EmptyState
          icon={History}
          title="Todavía no hay actividad"
          description="Cada carga, limpieza, análisis y consulta al asistente quedará registrada aquí, con su detalle de antes y después."
          ctaLabel="Cargar mis datos"
          ctaTo="/estandarizacion"
        />
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Historial"
        subtitle="Tus archivos y toda la actividad de la cuenta. Retoma un dataset para seguir trabajando donde quedaste."
      />

      {deleteNotice && (
        <div className="mb-5 flex items-start gap-2 rounded-lg border border-green/30 bg-green/[0.08] px-4 py-3 text-sm text-navy">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green" />
          <p className="min-w-0 [overflow-wrap:anywhere] lg:[overflow-wrap:normal]">{deleteNotice}</p>
        </div>
      )}

      <div className="grid w-full min-w-0 max-w-full items-start gap-6 overflow-x-hidden lg:overflow-x-visible xl:grid-cols-[minmax(0,1fr)_360px]">
        {/* Archivos cargados */}
        <Card className="h-fit min-w-0 max-w-full overflow-hidden lg:overflow-visible">
          <h2 ref={listHeadingRef} tabIndex={-1} className="text-base font-semibold text-navy outline-none">
            Archivos cargados
          </h2>
          <p className="mt-0.5 text-sm text-navy/60">
            Retomar descarga el archivo desde Storage y lo deja listo en Limpieza.
          </p>
          {resumeError && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-coral/40 bg-coral/10 px-3 py-2 text-xs text-coral">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <p className="min-w-0 [overflow-wrap:anywhere] lg:[overflow-wrap:normal]">{resumeError}</p>
            </div>
          )}
          <div className="mt-4 min-w-0 max-w-full space-y-3 lg:hidden">
            {(datasets ?? []).map((dataset) => {
              const badge = STATUS_BADGE[dataset.status]
              const source = sourceBadge(dataset.source)
              return (
                <article
                  key={dataset.id}
                  className="min-w-0 rounded-lg border border-navy/10 bg-navy/[0.015] p-3"
                >
                  <div className="flex min-w-0 items-start gap-2">
                    <FileSpreadsheet className="mt-0.5 h-4.5 w-4.5 shrink-0 text-green" />
                    <p className="min-w-0 [overflow-wrap:anywhere] text-sm font-semibold leading-snug text-navy">
                      {dataset.name}
                    </p>
                  </div>

                  <div className="mt-3 flex min-w-0 flex-wrap items-center gap-2">
                    <Badge tone={source.tone}>{source.label}</Badge>
                    <Badge tone={badge.tone}>{badge.label}</Badge>
                  </div>

                  <dl className="mt-3 min-w-0 divide-y divide-navy/5 border-y border-navy/5 text-xs">
                    <div className="flex min-w-0 items-start justify-between gap-3 py-2">
                      <dt className="shrink-0 text-navy/45">Fecha</dt>
                      <dd className="min-w-0 break-words text-right text-navy/75">
                        {formatDateTime(new Date(dataset.created_at))}
                      </dd>
                    </div>
                    <div className="flex min-w-0 items-start justify-between gap-3 py-2">
                      <dt className="shrink-0 text-navy/45">Filas</dt>
                      <dd className="min-w-0 text-right text-navy/75">
                        {dataset.rows != null ? formatNumber(dataset.rows) : '—'}
                      </dd>
                    </div>
                    <div className="flex min-w-0 items-start justify-between gap-3 py-2">
                      <dt className="shrink-0 text-navy/45">Calidad</dt>
                      <dd className="min-w-0 text-right text-navy/75">
                        {dataset.quality != null ? `${formatNumber(dataset.quality)}%` : '—'}
                      </dd>
                    </div>
                  </dl>

                  <div className="mt-3 flex min-w-0 items-center gap-2 border-t border-navy/10 pt-3">
                    {dataset.storage_path ? (
                      <button
                        onClick={() => void handleResume(dataset)}
                        disabled={resuming !== null || deleting}
                        className="inline-flex min-w-0 flex-1 items-center justify-center gap-1.5 rounded-lg border border-teal/50 px-3 py-2 text-xs font-semibold text-teal transition-colors hover:bg-teal hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {resuming === dataset.id ? (
                          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                        ) : (
                          <RotateCcw className="h-3.5 w-3.5 shrink-0" />
                        )}
                        Retomar
                      </button>
                    ) : (
                      <span className="min-w-0 flex-1 text-xs text-navy/40">
                        Sin archivo en Storage
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={(event) => {
                        returnFocusRef.current = event.currentTarget
                        setDeleteError(null)
                        setDeleteTarget(dataset)
                      }}
                      disabled={resuming !== null || deleting}
                      aria-label={`Eliminar archivo ${dataset.name}`}
                      title={`Eliminar archivo ${dataset.name}`}
                      className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-coral/35 text-coral transition-colors hover:bg-coral/10 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </article>
              )
            })}
            {(datasets?.length ?? 0) === 0 && (
              <p className="text-sm text-navy/50">Aún no hay archivos guardados.</p>
            )}
          </div>

          <div className="mt-4 hidden overflow-x-auto lg:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-navy/10 text-left text-xs font-semibold uppercase tracking-wide text-navy/50">
                  <th className="pb-2 pr-4">Archivo</th>
                  <th className="pb-2 pr-4">Fuente</th>
                  <th className="pb-2 pr-4">Fecha</th>
                  <th className="pb-2 pr-4">Filas</th>
                  <th className="pb-2 pr-4">Calidad</th>
                  <th className="pb-2 pr-4">Estado</th>
                  <th className="pb-2">Acción</th>
                </tr>
              </thead>
              <tbody>
                {(datasets ?? []).map((dataset) => {
                  const badge = STATUS_BADGE[dataset.status]
                  const source = sourceBadge(dataset.source)
                  return (
                    <tr key={dataset.id} className="border-b border-navy/5">
                      <td className="max-w-56 py-3 pr-4">
                        <div className="flex items-center gap-2 font-medium text-navy">
                          <FileSpreadsheet className="h-4.5 w-4.5 shrink-0 text-green" />
                          <span className="truncate">{dataset.name}</span>
                        </div>
                      </td>
                      <td className="whitespace-nowrap py-3 pr-4">
                        <Badge tone={source.tone}>{source.label}</Badge>
                      </td>
                      <td className="whitespace-nowrap py-3 pr-4 text-navy/70">
                        {formatDateTime(new Date(dataset.created_at))}
                      </td>
                      <td className="py-3 pr-4 text-navy/70">
                        {dataset.rows != null ? formatNumber(dataset.rows) : '—'}
                      </td>
                      <td className="py-3 pr-4 text-navy/70">
                        {dataset.quality != null ? `${formatNumber(dataset.quality)}%` : '—'}
                      </td>
                      <td className="py-3 pr-4">
                        <Badge tone={badge.tone}>{badge.label}</Badge>
                      </td>
                      <td className="py-3">
                        <div className="flex min-w-max items-center gap-2">
                          {dataset.storage_path ? (
                            <button
                              onClick={() => void handleResume(dataset)}
                              disabled={resuming !== null || deleting}
                              className="inline-flex items-center gap-1.5 rounded-lg border border-teal/50 px-3 py-1.5 text-xs font-semibold text-teal transition-colors hover:bg-teal hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {resuming === dataset.id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <RotateCcw className="h-3.5 w-3.5" />
                              )}
                              Retomar
                            </button>
                          ) : (
                            <span className="text-xs text-navy/40">Sin archivo en Storage</span>
                          )}
                          <button
                            type="button"
                            onClick={(event) => {
                              returnFocusRef.current = event.currentTarget
                              setDeleteError(null)
                              setDeleteTarget(dataset)
                            }}
                            disabled={resuming !== null || deleting}
                            aria-label={`Eliminar archivo ${dataset.name}`}
                            title={`Eliminar archivo ${dataset.name}`}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-coral/35 text-coral transition-colors hover:bg-coral/10 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {(datasets?.length ?? 0) === 0 && (
              <p className="mt-3 text-sm text-navy/50">Aún no hay archivos guardados.</p>
            )}
          </div>
        </Card>

        {/* Columna derecha: actividad + análisis guardados */}
        <div className="flex min-w-0 max-w-full flex-col gap-6">
          {/* Actividad */}
          <Card className="h-fit min-w-0 max-w-full overflow-hidden lg:overflow-visible">
            <h2 className="text-base font-semibold text-navy">Actividad reciente</h2>
            <ul className="mt-4 space-y-4">
              {(activity ?? []).map((item) => {
                const meta = ACTIVITY_META[item.activity_type]
                const description = sanitizeActivityDescription(item.description)
                return (
                  <li key={item.id} className="flex items-start gap-3">
                    <div
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${meta.tone}`}
                    >
                      <meta.icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold uppercase tracking-wide text-navy/45">
                        {meta.label}
                      </p>
                      <p className="truncate text-sm text-navy" title={description}>
                        {description}
                      </p>
                      <p
                        className="mt-0.5 text-xs text-navy/50"
                        title={formatDateTime(new Date(item.created_at))}
                      >
                        {formatRelativeTime(new Date(item.created_at))}
                      </p>
                    </div>
                  </li>
                )
              })}
            </ul>
            {(activity?.length ?? 0) === 0 && (
              <p className="mt-3 text-sm text-navy/50">Sin actividad registrada todavía.</p>
            )}
          </Card>

          {/* Análisis guardados (Explorar datos → "Guardar análisis") */}
          <Card className="h-fit min-w-0 max-w-full overflow-hidden lg:overflow-visible">
            <div className="flex items-center gap-2">
              <Search className="h-4.5 w-4.5 text-navy/70" />
              <h2 className="text-base font-semibold text-navy">Análisis guardados</h2>
            </div>
            <ul className="mt-4 space-y-3">
              {(analyses ?? []).map((item) => {
                const expanded = expandedAnalysis === item.id
                const monetaryIntegrityVerified = hasVerifiedMonetaryIntegrity(item)
                return (
                  <li key={item.id} className="rounded-lg border border-navy/10 p-3">
                    <button
                      type="button"
                      onClick={() => setExpandedAnalysis(expanded ? null : item.id)}
                      className="flex w-full items-start justify-between gap-2 text-left"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-navy" title={item.name}>
                          {item.name}
                        </p>
                        <p className="mt-0.5 text-xs text-navy/50">
                          {formatDateTime(new Date(item.created_at))} ·{' '}
                          {monetaryIntegrityVerified
                            ? `${item.findings.length} hallazgo(s) · ${item.config?.moneda ?? 'moneda sin etiqueta'}`
                            : 'integridad monetaria sin verificar'}
                        </p>
                      </div>
                    </button>
                    {expanded && (
                      <div className="mt-3 space-y-2 border-t border-navy/10 pt-3">
                        {!monetaryIntegrityVerified ? (
                          <div className="flex gap-2 rounded-lg border border-gold/30 bg-gold/[0.08] p-2.5 text-xs leading-relaxed text-navy/70">
                            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
                            <p>
                              Este análisis fue guardado antes del control global de monedas.
                              Sus cifras y recomendaciones no se muestran porque no es posible
                              demostrar su integridad. Vuelve a ejecutarlo desde Explorar datos.
                            </p>
                          </div>
                        ) : item.findings.length > 0 ? (
                          <ul className="list-inside list-disc space-y-1 text-xs text-navy/70">
                            {item.findings.map((finding, index) => (
                              <li key={index}>{finding}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-xs text-navy/45">Sin hallazgos registrados.</p>
                        )}
                        {monetaryIntegrityVerified && item.recommendation && (
                          <p className="rounded-lg bg-gold/[0.08] p-2.5 text-xs leading-relaxed text-navy/70">
                            {item.recommendation.recomendacion}
                          </p>
                        )}
                        <button
                          type="button"
                          onClick={() => void handleDeleteAnalysis(item.id)}
                          disabled={deletingAnalysis === item.id}
                          className="mt-1 text-xs font-medium text-coral hover:underline disabled:opacity-50"
                        >
                          {deletingAnalysis === item.id ? 'Eliminando...' : 'Eliminar'}
                        </button>
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
            {(analyses?.length ?? 0) === 0 && (
              <p className="mt-3 text-sm text-navy/50">
                Aún no has guardado ningún análisis. Hazlo desde Explorar datos.
              </p>
            )}
          </Card>
        </div>
      </div>

      {deleteTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-navy-deep/55 p-4"
          role="presentation"
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-dataset-title"
            aria-describedby="delete-dataset-description"
            className="w-full max-w-lg rounded-lg bg-white p-6 shadow-2xl"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-coral/10 text-coral">
                <Trash2 className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <h2 id="delete-dataset-title" className="text-base font-semibold text-navy">
                  Eliminar archivo definitivamente
                </h2>
                <p id="delete-dataset-description" className="mt-2 min-w-0 text-sm leading-relaxed text-navy/65 [overflow-wrap:anywhere] lg:[overflow-wrap:normal]">
                  ¿Estás seguro de que quieres eliminar “{deleteTarget.name}”? Se borrará el
                  archivo de tu almacenamiento y su historial de limpieza. Esta acción no se
                  puede deshacer.
                </p>
              </div>
            </div>
            {deleteError && (
              <div className="mt-4 flex items-start gap-2 rounded-lg border border-coral/35 bg-coral/[0.07] px-3 py-2 text-xs text-coral">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <p>{deleteError}</p>
              </div>
            )}
            <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                ref={cancelDeleteRef}
                type="button"
                onClick={closeDeleteDialog}
                disabled={deleting}
                className="rounded-lg border border-navy/20 px-4 py-2.5 text-sm font-semibold text-navy transition-colors hover:bg-navy/5 disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                ref={confirmDeleteRef}
                type="button"
                onClick={() => void handleDelete()}
                disabled={deleting}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-coral px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-coral/90 disabled:cursor-wait disabled:opacity-60"
              >
                {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                {deleting ? 'Eliminando por etapas…' : 'Eliminar definitivamente'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
