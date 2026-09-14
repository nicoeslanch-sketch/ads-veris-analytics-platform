import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CalendarDays, Search } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import EmptyState from '../components/ui/EmptyState'
import ActiveSheetSelector from '../components/ActiveSheetSelector'
import RelationshipWorkspace from '../components/relationships/RelationshipWorkspace'
import BusinessFilterBar from '../components/BusinessFilterBar'
import AnalysisLoadingPanel from '../components/AnalysisLoadingPanel'
import ExplorationAnalysis from '../components/ExplorationAnalysis'
import { ALL_PERIOD, monthPeriod, useDataset } from '../data/DatasetContext'
import { useDemo } from '../demo/DemoContext'
import { DemoEmptyActions } from '../demo/DemoBanner'
import { metricsSnapshotMatchesScope, serializedAnalysisScope } from '../lib/multiSheet'
import { getCachedMetrics, metricsCacheKey, requestMetrics } from '../lib/analysisCache'
import { ApiError, apiPostJob, buildDatasetForm } from '../lib/api'
import { saveAnalysis } from '../lib/datasets'
import { setActiveCurrency } from '../lib/format'
import type { AnalysisScope, MetricsResult } from '../lib/types'

export default function Explorar() {
  // El "Rango" de Explorar comparte estado con el selector de periodo global
  // del topbar (Bug #8): antes eran dos filtros independientes y cambiar uno
  // no se reflejaba en el otro ni en el gráfico/hallazgos de esta página.
  const { file, cleaning, datasetId, storagePath, uploadedAt, metrics: contextMetrics, monthsAvailable, setMonthsAvailable, mappingOverride, sheet, sheetManifest, analysisScope, businessFilters, setBusinessFilters, eliminarDuplicados, period: rango, setPeriod: setRango } = useDataset()
  // Fase 14: la demo ficticia sirve métricas congeladas del bundle (sin backend)
  const demo = useDemo()
  // "Relación manual" (modo `join`) reemplaza el contenido de la página por el
  // workspace de relaciones, igual que en Resumen.
  const [selectorMode, setSelectorMode] = useState<AnalysisScope['mode']>(
    analysisScope?.mode ?? 'single',
  )
  const relationshipMode = selectorMode === 'join'
  const [openRelationsNonce, setOpenRelationsNonce] = useState(0)
  const ready = Boolean(file && cleaning) || demo.active


  const [fetchedMetrics, setMetrics] = useState<MetricsResult | null>(null)
  const metrics = demo.active ? demo.metrics : fetchedMetrics
  const visiblePeriod = demo.active ? ALL_PERIOD : rango
  const standaloneBusinessAvailable = (
    analysisScope?.mode === 'single'
    && metrics?.tipo_analisis === 'ventas'
    && Boolean(metrics.analisis_negocio)
  )
  const businessUnavailable = (
    selectorMode === 'append_join'
    && analysisScope?.mode !== 'append_join'
    && !standaloneBusinessAvailable
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Fase 11 §9.3: "Reintentar" tras un timeout o corte de red
  const [retryTick, setRetryTick] = useState(0)
  const lastFetchKey = useRef<string | null>(null)
  const latestRequest = useRef(0)
  const requestAbortRef = useRef<AbortController | null>(null)

  const cancelMetrics = () => {
    requestAbortRef.current?.abort()
    requestAbortRef.current = null
    latestRequest.current += 1
    lastFetchKey.current = null
    setLoading(false)
    setError('La carga fue cancelada. Puedes reintentar cuando quieras.')
  }


  useEffect(() => {
    setMetrics(null)
  }, [analysisScope, sheet])

  // Métricas del rango seleccionado (uploadedAt distingue cargas con igual nombre)
  useEffect(() => {
    if (demo.active) return // la demo no consulta /metrics: snapshot congelado
    if (!file || !cleaning) return
    const datasetKey = datasetId ?? storagePath ?? String(uploadedAt?.getTime() ?? 0)
    // Mapeo manual y reintento en la clave: cambiar el mapeo refresca el análisis
    const key = metricsCacheKey({
      dataset: datasetKey,
      dateFrom: rango.from,
      dateTo: rango.to,
      sheet,
      analysisScope,
      businessFilters,
      mapping: mappingOverride,
      eliminarDuplicados,
      revision: cleaning.revision,
      rules: cleaning.reglas_activas,
      directed: cleaning.dirigida,
      manifest: sheetManifest,
      retry: retryTick,
    })
    lastFetchKey.current = key
    const cached = getCachedMetrics(key)
    if (cached) {
      setMetrics(cached)
      setActiveCurrency(cached.moneda)
      if (monthsAvailable.length === 0) {
        setMonthsAvailable(cached.periodo.meses_disponibles)
      }
      setError(null)
      setLoading(false)
      return
    }
    const snapshotMatchesRange = Boolean(
      contextMetrics &&
      metricsSnapshotMatchesScope(contextMetrics.analysis_scope, analysisScope, sheet) &&
      !rango.from &&
      !rango.to &&
      Object.keys(businessFilters).length === 0 &&
      !contextMetrics.periodo.desde &&
      !contextMetrics.periodo.hasta,
    )
    if (snapshotMatchesRange && contextMetrics) {
      setMetrics(contextMetrics)
      setActiveCurrency(contextMetrics.moneda)
      if (monthsAvailable.length === 0) {
        setMonthsAvailable(contextMetrics.periodo.meses_disponibles)
      }
      setError(null)
      setLoading(false)
      // Fase 13: este camino también libera su clave al desmontar — con el
      // doble montaje de StrictMode la clave quedaba "ya pedida" mientras otro
      // efecto vaciaba las métricas, y los presets no se adaptaban al archivo.
      return () => {
        if (lastFetchKey.current === key) lastFetchKey.current = null
      }
    }
    requestAbortRef.current?.abort()
    const controller = new AbortController()
    requestAbortRef.current = controller
    const timingStarted = performance.now()
    console.info('[ADS Veris timing] metrics:start', { page: 'explorar', sheet: sheet ?? null })
    const requestId = latestRequest.current + 1
    latestRequest.current = requestId
    setLoading(true)
    setError(null)
    const fields: Record<string, string> = {
      eliminar_duplicados: String(eliminarDuplicados),
      ...(datasetId ? { dataset_id: datasetId } : {}),
    }
    if (mappingOverride) fields.mapping = JSON.stringify(mappingOverride)
    fields.rules = JSON.stringify(cleaning.reglas_activas)
    if (cleaning.revision != null) fields.revision = String(cleaning.revision)
    if (cleaning.dirigida) {
      fields.scope = JSON.stringify({
        incluir: cleaning.dirigida.columnas_incluir,
        excluir: cleaning.dirigida.columnas_excluir,
      })
    }
    if (sheet) fields.sheet = sheet
    if (sheetManifest && analysisScope) {
      fields.manifest = JSON.stringify(sheetManifest)
      const serializedScope = serializedAnalysisScope(analysisScope)
      if (serializedScope) fields.analysis_scope = serializedScope
    }
    if (Object.keys(businessFilters).length > 0) {
      fields.business_filters = JSON.stringify(businessFilters)
    }
    if (rango.from) fields.date_from = rango.from
    if (rango.to) fields.date_to = rango.to
    requestMetrics(
      key,
      (signal) => apiPostJob<MetricsResult>(
        '/analysis/jobs/metrics',
        buildDatasetForm(file, storagePath, fields),
        { signal },
      ),
      controller.signal,
    )
      .then((result) => {
        if (latestRequest.current !== requestId || controller.signal.aborted) return
        setMetrics(result)
        setActiveCurrency(result.moneda)
        if (monthsAvailable.length === 0 && result.periodo.meses_disponibles.length > 0) {
          setMonthsAvailable(result.periodo.meses_disponibles)
        }
      })
      .catch((err) => {
        if (latestRequest.current !== requestId || controller.signal.aborted) return
        // Anular la clave: sin esto el próximo render "cree" que ya se pidió
        // y la página queda vacía hasta recargar (Fase 11 §9.3).
        lastFetchKey.current = null
        setError(err instanceof ApiError ? err.message : 'No se pudo calcular el análisis.')
      })
      .finally(() => {
        console.info('[ADS Veris timing] metrics:end', {
          page: 'explorar',
          sheet: sheet ?? null,
          durationMs: Math.round(performance.now() - timingStarted),
        })
        if (requestAbortRef.current === controller) requestAbortRef.current = null
        if (latestRequest.current === requestId && !controller.signal.aborted) setLoading(false)
      })
    return () => {
      controller.abort()
      // Fase 12b: liberar la clave al abortar (StrictMode/remontaje) — si
      // queda "ya pedida" con la petición abortada, la página no carga jamás.
      if (lastFetchKey.current === key) lastFetchKey.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demo.active, file, datasetId, storagePath, cleaning, contextMetrics, uploadedAt, rango, sheet, sheetManifest, analysisScope, businessFilters, mappingOverride, eliminarDuplicados, retryTick])


  const guardarAnalisis = (title: string, findings: string[]) => saveAnalysis(
    datasetId, title,
    { rango: rango.label, moneda: metrics?.moneda, analysis_scope: analysisScope },
    findings, null,
  )

  if (!ready) return (
    <>
      <PageHeader title="Explorar datos" subtitle="Lectura, evidencia y límites de tus datos." />
      <EmptyState icon={Search} title="No hay datos que explorar todavía" description="El análisis requiere una base limpia." ctaLabel="Cargar mis datos" ctaTo="/estandarizacion">
        <DemoEmptyActions />
      </EmptyState>
    </>
  )

  return (
    <>
      <PageHeader title="Explorar datos" subtitle="Lectura, evidencia y límites de tus datos." />
      <ActiveSheetSelector onModeChange={setSelectorMode} openRelationsNonce={openRelationsNonce} />
      {businessUnavailable ? (
        <EmptyState icon={Search} title="No existen conexiones seguras entre las hojas." description="Sin correspondencias validadas no se construye un resultado conjunto." ctaLabel="Relacionar hojas a mano" onCta={() => setOpenRelationsNonce((nonce) => nonce + 1)} />
      ) : relationshipMode && !demo.active ? (
        <>
          {metrics && !metrics.moneda_mixta && <ExplorationAnalysis metrics={metrics} from={visiblePeriod.from} to={visiblePeriod.to} />}
          <details className="mt-6 border-t border-navy/10 pt-4" open={!metrics}>
            <summary className="cursor-pointer text-sm font-semibold text-navy">Comprobar y ajustar la relación entre hojas</summary>
            <div className="mt-4"><RelationshipWorkspace /></div>
          </details>
        </>
      ) : (
        <>
          <div className="mb-5 flex min-w-0 flex-wrap items-center gap-3">
            <label className="flex min-w-0 max-w-full flex-1 items-center gap-2 text-sm font-medium text-navy sm:flex-none">
              <CalendarDays className="h-4 w-4 shrink-0 text-teal" aria-hidden />
              Período
              <select aria-label="Período del análisis" disabled={demo.active} value={visiblePeriod.from?.slice(0, 7) ?? 'all'} onChange={(event) => setRango(event.target.value === 'all' ? ALL_PERIOD : monthPeriod(event.target.value))} className="min-w-0 max-w-full flex-1 rounded-lg border border-navy/20 bg-white px-3 py-2 text-sm disabled:opacity-60 sm:flex-none">
                <option value="all">Todo el período</option>
                {monthsAvailable.map((month) => <option key={month} value={month}>{month}</option>)}
              </select>
            </label>
            {loading && <span role="status" className="text-xs text-navy/60">Actualizando el análisis...</span>}
          </div>
          {metrics?.analisis_negocio?.filtros && <BusinessFilterBar options={metrics.analisis_negocio.filtros.disponibles} value={businessFilters} disabled={loading} onChange={setBusinessFilters} />}
          {error && <div role="alert" className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-coral/30 px-4 py-3 text-sm text-coral"><p className="min-w-0 break-words">{error}</p><button type="button" onClick={() => setRetryTick((tick) => tick + 1)} className="font-semibold underline">Reintentar</button></div>}
          {loading ? <AnalysisLoadingPanel operation={`Preparando el análisis${sheet ? ` de ${sheet}` : ''}`} detail="Se conserva la limpieza realizada." onCancel={cancelMetrics} /> : error ? null : metrics?.moneda_mixta ? (
            <EmptyState icon={AlertTriangle} title="Exploración monetaria bloqueada" description="Hay monedas incompatibles. Separa las monedas antes de comparar sus importes." ctaLabel="Revisar en Limpieza" ctaTo="/limpieza" />
          ) : metrics ? <ExplorationAnalysis key={`${sheet}-${metrics.tipo_analisis}-${visiblePeriod.from}-${visiblePeriod.to}`} metrics={metrics} from={visiblePeriod.from} to={visiblePeriod.to} onSave={demo.active ? undefined : guardarAnalisis} /> : null}
          {demo.active && <p className="mt-5 text-xs text-navy/50">En la demo, el asistente con IA está desactivado. Esta lectura utiliza únicamente las cifras ficticias del ejemplo.</p>}
        </>
      )}
    </>
  )
}
