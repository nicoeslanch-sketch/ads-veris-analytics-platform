/**
 * Historial (SPEC §7 — Fase 5, MVP).
 *
 * Trazabilidad de la cuenta: archivos cargados (con estado, calidad y
 * "Retomar" para rehidratar la sesión desde Supabase Storage) + actividad
 * completa (cargas, estandarizaciones, limpiezas, análisis, chat).
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  Eraser,
  FileSpreadsheet,
  History,
  Lightbulb,
  Loader2,
  MessageCircle,
  RotateCcw,
  Search,
  Sparkles,
  Upload,
  type LucideIcon,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import EmptyState from '../components/ui/EmptyState'
import { useDataset } from '../data/DatasetContext'
import { apiPost, buildDatasetForm, ApiError } from '../lib/api'
import {
  downloadDatasetFile,
  fetchActivity,
  fetchDatasets,
  fetchLatestCleaningRules,
  type ActivityRow,
  type ActivityType,
  type DatasetRow,
} from '../lib/history'
import { supabaseConfigured } from '../lib/supabase'
import { formatDateTime, formatNumber } from '../lib/format'
import { DEFAULT_RULES, type CleanResult, type StandardizeResult } from '../lib/types'

const ACTIVITY_META: Record<ActivityType, { label: string; icon: LucideIcon; tone: string }> = {
  carga: { label: 'Carga', icon: Upload, tone: 'bg-teal/10 text-teal' },
  estandarizacion: { label: 'Estandarización', icon: Sparkles, tone: 'bg-gold/15 text-gold' },
  limpieza: { label: 'Limpieza', icon: Eraser, tone: 'bg-green/10 text-green' },
  analisis: { label: 'Análisis', icon: Search, tone: 'bg-navy/10 text-navy' },
  chat: { label: 'Chat IA', icon: MessageCircle, tone: 'bg-teal/10 text-teal' },
  recomendacion: { label: 'Recomendación', icon: Lightbulb, tone: 'bg-gold/15 text-gold' },
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
  const { setUploaded, setStandardization, setCleaning } = useDataset()
  const navigate = useNavigate()

  const [datasets, setDatasets] = useState<DatasetRow[] | null>(null)
  const [activity, setActivity] = useState<ActivityRow[] | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [loading, setLoading] = useState(true)
  const [resuming, setResuming] = useState<string | null>(null)
  const [resumeError, setResumeError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchDatasets(), fetchActivity()]).then(([ds, act]) => {
      if (cancelled) return
      // 'error' ≠ vacío: un fallo de Supabase no debe verse como "sin actividad"
      setLoadError(ds === 'error' || act === 'error')
      setDatasets(ds === 'error' ? [] : ds)
      setActivity(act === 'error' ? [] : act)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

  /** Rehidrata la sesión: descarga el archivo de Storage y re-estandariza.
   * Si el dataset ya estaba limpio, re-aplica la limpieza para dejar el
   * dashboard y el asistente operativos de inmediato. */
  const handleResume = async (dataset: DatasetRow) => {
    if (!dataset.storage_path) return
    setResuming(dataset.id)
    setResumeError(null)
    try {
      const file = await downloadDatasetFile(dataset.storage_path, dataset.name)
      if (!file) {
        setResumeError('No se pudo descargar el archivo desde Storage.')
        return
      }
      setUploaded(file, dataset.id, dataset.storage_path)
      const result = await apiPost<StandardizeResult>(
        '/standardize',
        buildDatasetForm(file, dataset.storage_path),
      )
      setStandardization(result)
      if (dataset.status === 'limpio') {
        // Continuar con las reglas reales del último cleaning_job cuando existan.
        const savedRules = await fetchLatestCleaningRules(dataset.id)
        const usedDefaultRules = !savedRules
        const cleaned = await apiPost<CleanResult>(
          '/clean',
          buildDatasetForm(file, dataset.storage_path, {
            apply: 'true',
            rules: JSON.stringify(savedRules ?? DEFAULT_RULES),
          }),
        )
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

  const hasData = (datasets?.length ?? 0) > 0 || (activity?.length ?? 0) > 0

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

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        {/* Archivos cargados */}
        <Card className="h-fit min-w-0">
          <h2 className="text-base font-semibold text-navy">Archivos cargados</h2>
          <p className="mt-0.5 text-sm text-navy/60">
            Retomar descarga el archivo desde Storage y lo deja listo en Limpieza.
          </p>
          {resumeError && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-coral/40 bg-coral/10 px-3 py-2 text-xs text-coral">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <p>{resumeError}</p>
            </div>
          )}
          <div className="mt-4 overflow-x-auto">
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
                        {dataset.storage_path ? (
                          <button
                            onClick={() => void handleResume(dataset)}
                            disabled={resuming !== null}
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

        {/* Actividad */}
        <Card className="h-fit">
          <h2 className="text-base font-semibold text-navy">Actividad reciente</h2>
          <ul className="mt-4 space-y-4">
            {(activity ?? []).map((item) => {
              const meta = ACTIVITY_META[item.activity_type]
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
                    <p className="truncate text-sm text-navy" title={item.description}>
                      {item.description}
                    </p>
                    <p className="mt-0.5 text-xs text-navy/50">
                      {formatDateTime(new Date(item.created_at))}
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
      </div>
    </>
  )
}
