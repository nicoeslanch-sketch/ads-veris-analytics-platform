import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Coins,
  HeartPulse,
  Info,
  LayoutDashboard,
  Loader2,
  Percent,
  Receipt,
  TrendingUp,
  Upload,
  Wallet,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import EmptyState from '../components/ui/EmptyState'
import ActiveSheetSelector from '../components/ActiveSheetSelector'
import ProductCatalogSummary from '../components/ProductCatalogSummary'
import AdaptiveProfileSummary from '../components/AdaptiveProfileSummary'
import BusinessAnalysisPanel from '../components/BusinessAnalysisPanel'
import { useAuth } from '../auth/AuthContext'
import { fullRangePeriod, useDataset } from '../data/DatasetContext'
import { useDemo } from '../demo/DemoContext'
import { DemoEmptyActions } from '../demo/DemoBanner'
import { apiPost, buildDatasetForm, ApiError } from '../lib/api'
import { AXIS_INK, CATEGORICAL, CHART, GRID_STROKE, chartColorForKey, formatCLPCompact, formatMonthShort, shouldSplitFinancialScale, truncateLabel } from '../lib/charts'
import { formatCLP, formatNumber, setActiveCurrency } from '../lib/format'
import { soloMesesCompletos } from '../lib/partial'
import { getCachedMetrics, metricsCacheKey, requestMetrics } from '../lib/analysisCache'
import { summaryContentKind } from '../lib/metrics'
import { analysisScopesEqual, serializedAnalysisScope } from '../lib/multiSheet'
import type { MetricsResult } from '../lib/types'

type UsableMonetaryKpis = MetricsResult['kpis'] & {
  ingresos_totales: NonNullable<MetricsResult['kpis']['ingresos_totales']>
  ticket_promedio: number
}

function hasUsableMonetaryKpis(
  kpis: MetricsResult['kpis'] | undefined,
): kpis is UsableMonetaryKpis {
  return Boolean(kpis?.ingresos_totales && kpis.ticket_promedio != null)
}

/** Indicadores operativos del negocio, calculados de los datos reales del
 * archivo (los ratios de balance —ROA, ROE, liquidez— requieren conectar
 * datos de balance y quedan como nota hasta entonces). */
function buildOperationalIndicators(m: MetricsResult): Array<{ label: string; value: string; hint?: string }> {
  const kpis = m.kpis
  const evo = m.evolucion_mensual
  const items: Array<{ label: string; value: string; hint?: string }> = []

  // Fase 12b §12: si hay filas sin monto legible, el ticket lo dice — el
  // promedio se calcula sobre menos registros que el total.
  const conMonto = kpis.registros_con_monto
  if (kpis.ticket_promedio != null) {
    items.push({
      label: 'Ticket promedio',
      value: formatCLP(kpis.ticket_promedio),
      hint:
        conMonto != null && conMonto < kpis.transacciones
          ? `sobre ${formatNumber(conMonto)} de ${formatNumber(kpis.transacciones)} registros con monto`
          : 'por registro',
    })
  }
  // §11: sin una clave de transacción declarada, esto son FILAS del archivo.
  items.push({ label: 'Registros', value: formatNumber(kpis.transacciones), hint: 'filas en el periodo' })
  if (kpis.devoluciones) {
    items.push({
      label: 'Devoluciones / ajustes',
      value: formatCLP(kpis.devoluciones.monto),
      hint: `${formatNumber(kpis.devoluciones.filas)} monto(s) negativo(s) — los ingresos son netos`,
    })
  }
  if (kpis.unidades_totales != null) {
    items.push({ label: 'Unidades vendidas', value: formatNumber(kpis.unidades_totales) })
  }
  const completos = soloMesesCompletos(evo)
  if (completos.length >= 1) {
    // Fase 14: los meses PARCIALES no compiten como "mejor mes" ni definen el
    // crecimiento del periodo — un mes a medio llenar simulaba una caída.
    const best = completos.reduce((a, b) => (b.ingresos > a.ingresos ? b : a))
    items.push({
      label: 'Mejor mes',
      value: formatMonthShort(best.mes),
      hint: formatCLP(best.ingresos),
    })
    const first = completos[0]
    const last = completos[completos.length - 1]
    if (completos.length >= 2 && first.ingresos > 0) {
      const totalGrowth = ((last.ingresos - first.ingresos) / first.ingresos) * 100
      items.push({
        label: 'Crecimiento del periodo',
        value: `${totalGrowth >= 0 ? '+' : ''}${formatNumber(Math.round(totalGrowth * 10) / 10)}%`,
        hint: `${formatMonthShort(first.mes)} → ${formatMonthShort(last.mes)}${
          completos.length < evo.length ? ' (sin el mes incompleto)' : ''
        }`,
      })
    }
  }
  if (m.proyeccion) {
    const g = m.proyeccion.crecimiento_pct
    items.push({
      label: 'Tendencia mensual',
      value: `${g >= 0 ? '+' : ''}${formatNumber(Math.round(g * 10) / 10)}%`,
      hint: 'crecimiento promedio',
    })
  }
  const margen = kpis.margen_utilidad_pct?.valor
  if (margen != null) {
    items.push({
      label: 'Margen del periodo',
      value: `${formatNumber(Math.round(margen * 10) / 10)}%`,
      hint: 'utilidad / ingresos',
    })
  }
  // Fase 12: indicadores accionables de PyME — mejor día para dotación/horarios
  // y concentración de clientes (riesgo de depender de uno).
  const dias = m.por_dia_semana ?? []
  if (dias.length >= 2) {
    const mejorDia = dias.reduce((a, b) => (b.ingresos > a.ingresos ? b : a))
    items.push({
      label: 'Mejor día de venta',
      value: mejorDia.dia.charAt(0).toUpperCase() + mejorDia.dia.slice(1),
      hint: `${formatCLP(mejorDia.ingresos)} en el periodo`,
    })
  }
  if (m.clientes) {
    // Fase 12b §21: el % del principal es sobre las ventas CON cliente
    // identificado; si la cobertura es parcial, se dice explícito.
    const cobertura = m.clientes.cobertura_identificacion_pct
    const parcial = cobertura != null && cobertura < 95
    items.push({
      label: 'Clientes únicos',
      value: formatNumber(m.clientes.unicos),
      hint:
        m.clientes.concentracion_top_pct != null && m.clientes.unicos > 1
          ? `principal: ${formatNumber(m.clientes.concentracion_top_pct)}% de las ventas identificadas${
              parcial ? ` (identificación: ${formatNumber(cobertura)} % de los ingresos)` : ''
            }`
          : undefined,
    })
  }
  return items.slice(0, 10)
}

function Variation({
  pct,
  suffix = 'vs periodo anterior',
  points = false,
}: {
  pct: number | null
  suffix?: string
  points?: boolean
}) {
  if (pct === null) return <p className="text-xs text-navy/40">— sin periodo anterior</p>
  const positive = pct >= 0
  const Icon = positive ? ArrowUpRight : ArrowDownRight
  return (
    <p className={`flex items-center gap-1 text-xs font-semibold ${positive ? 'text-green' : 'text-coral'}`}>
      <Icon className="h-3.5 w-3.5" />
      {positive ? '+' : ''}
      {formatNumber(pct)}
      {points ? ' pts' : '%'}
      <span className="font-normal text-navy/45">{suffix}</span>
    </p>
  )
}

function Sparkline({ data, color }: { data: Array<{ v: number | null }>; color: string }) {
  if (data.filter((d) => d.v !== null).length < 2) return null
  return (
    <div className="h-9 w-24">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 2, bottom: 2, left: 2 }}>
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-navy/10 bg-white px-3 py-2 text-xs shadow-lg">
      {label && <p className="mb-1 font-semibold text-navy">{formatMonthShort(label)}</p>}
      {payload.map((entry) => (
        <p key={entry.name} className="flex items-center gap-1.5 text-navy/75">
          <span className="h-2 w-2 rounded-full" style={{ background: entry.color }} />
          {entry.name}: <span className="font-semibold text-navy">{formatCLP(entry.value)}</span>
        </p>
      ))}
    </div>
  )
}

export default function Resumen() {
  const { user } = useAuth()
  const location = useLocation()
  const { file, datasetId, storagePath, cleaning, metrics: contextMetrics, uploadedAt, period, setPeriod, setMonthsAvailable, setMetrics: setContextMetrics, mappingOverride, sheet, sheetManifest, analysisScope, eliminarDuplicados } = useDataset()
  // Fase 14: la demo ficticia entrega métricas congeladas del bundle — jamás
  // escribe en el DatasetContext ni llama al backend.
  const demo = useDemo()
  const [fetchedMetrics, setMetrics] = useState<MetricsResult | null>(null)
  const metrics = demo.active ? demo.metrics : fetchedMetrics
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Fase 11 §9.3: tras un fallo (timeout, red) el usuario puede reintentar sin
  // recargar la página — el botón incrementa retryTick y el efecto vuelve a correr.
  const [retryTick, setRetryTick] = useState(0)
  const defaultPeriodSet = useRef(false)
  const lastFetchKey = useRef<string | null>(null)
  const lastDatasetKey = useRef<string | null>(null)
  const latestRequest = useRef(0)

  const firstName =
    ((user?.user_metadata?.full_name as string | undefined) ?? '').trim().split(' ')[0] || null
  const ready = Boolean(file && cleaning)
  const resumeWarning =
    typeof (location.state as { resumeWarning?: unknown } | null)?.resumeWarning === 'string'
      ? ((location.state as { resumeWarning: string }).resumeWarning)
      : null

  useEffect(() => {
    setMetrics(null)
  }, [analysisScope, sheet])

  useEffect(() => {
    if (demo.active) return // la demo no consulta /metrics: snapshot congelado
    if (!file || !cleaning) return
    // uploadedAt distingue dos cargas distintas aunque el archivo se llame igual
    const datasetKey = datasetId ?? storagePath ?? String(uploadedAt?.getTime() ?? 0)
    // Con un dataset nuevo, el auto-mes por defecto debe volver a aplicarse
    if (lastDatasetKey.current !== datasetKey) {
      lastDatasetKey.current = datasetKey
      defaultPeriodSet.current = false
    }
    // El mapeo manual y el reintento forman parte de la clave: cambiar el mapeo
    // en Limpieza refresca el dashboard, y "Reintentar" fuerza una nueva llamada.
    const key = metricsCacheKey({
      dataset: datasetKey,
      dateFrom: period.from,
      dateTo: period.to,
      sheet,
      analysisScope,
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
      setMonthsAvailable(cached.periodo.meses_disponibles)
      setError(null)
      setLoading(false)
      return
    }
    const snapshotMatchesPeriod = Boolean(
      contextMetrics &&
      analysisScopesEqual(contextMetrics.analysis_scope, analysisScope) &&
      !period.from &&
      !period.to &&
      !contextMetrics.periodo.desde &&
      !contextMetrics.periodo.hasta,
    )
    if (snapshotMatchesPeriod && contextMetrics) {
      defaultPeriodSet.current = true
      setMetrics(contextMetrics)
      setActiveCurrency(contextMetrics.moneda)
      setMonthsAvailable(contextMetrics.periodo.meses_disponibles)
      setError(null)
      setLoading(false)
      return
    }
    const controller = new AbortController()
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
    if (period.from) fields.date_from = period.from
    if (period.to) fields.date_to = period.to
    requestMetrics(
      key,
      () => apiPost<MetricsResult>('/metrics', buildDatasetForm(file, storagePath, fields)),
    )
      .then((result) => {
        if (latestRequest.current !== requestId || controller.signal.aborted) return
        setMetrics(result)
        setActiveCurrency(result.moneda)
        // El contexto compartido (Alertas/Reportes/IA) solo cachea métricas
        // del periodo COMPLETO — jamás el mes filtrado del Resumen (Fase 10 §5).
        if (!period.from && !period.to) setContextMetrics(result)
        const months = result.periodo.meses_disponibles
        setMonthsAvailable(months)
        // Al entrar por primera vez, mostrar el rango completo del dataset
        // (Bug #2: antes se fijaba en un solo mes y el dashboard escondía
        // datos reales del archivo sin ningún aviso).
        if (!defaultPeriodSet.current && months.length > 1 && !period.from) {
          defaultPeriodSet.current = true
          setPeriod(fullRangePeriod(months))
        }
      })
      .catch((err) => {
        if (latestRequest.current !== requestId || controller.signal.aborted) return
        // Si falla, la clave se anula para que el próximo intento sí ejecute
        // (antes quedaba "marcada como hecha" y la página se veía vacía para siempre).
        lastFetchKey.current = null
        setError(err instanceof ApiError ? err.message : 'No se pudieron calcular las métricas.')
      })
      .finally(() => {
        if (latestRequest.current === requestId && !controller.signal.aborted) setLoading(false)
      })
    return () => {
      controller.abort()
      // Fase 12b: al abortar (StrictMode/remontaje) la clave se libera — si
      // queda "ya pedida" con la petición abortada, la página no carga jamás.
      if (lastFetchKey.current === key) lastFetchKey.current = null
    }
  }, [demo.active, file, datasetId, storagePath, cleaning, contextMetrics, uploadedAt, period, sheet, sheetManifest, analysisScope, mappingOverride, eliminarDuplicados, retryTick, setContextMetrics, setMonthsAvailable, setPeriod])

  if (!ready && !demo.active) {
    return (
      <>
        <PageHeader
          title={firstName ? `Bienvenido, ${firstName} 👋` : 'Bienvenido 👋'}
          subtitle="Este es el resumen general de tu negocio."
        />
        <EmptyState
          icon={LayoutDashboard}
          title="Aún no hay datos para mostrar"
          description="Tu dashboard con KPIs, indicadores y ratios aparecerá aquí cuando cargues y limpies tu primer archivo de datos. Todo parte de los datos."
          ctaLabel="Cargar mis datos"
          ctaTo="/estandarizacion"
        >
          {/* Fase 14: conocer la plataforma sin datos propios */}
          <DemoEmptyActions />
        </EmptyState>
      </>
    )
  }

  // El backend reemplaza toda suma monetaria por null cuando hay monedas
  // incompatibles. No construir tarjetas antes de mostrar el bloqueo global.
  const adaptiveProfile = Boolean(metrics?.analisis_campanas || metrics?.analisis_inventario || metrics?.analisis_generico)
  const contentKind = metrics ? summaryContentKind(metrics) : null
  const candidateKpis = metrics?.moneda_mixta || metrics?.analisis_productos || adaptiveProfile
    ? undefined
    : metrics?.kpis
  const kpis = hasUsableMonetaryKpis(candidateKpis) ? candidateKpis : undefined
  const evolution = metrics?.evolucion_mensual ?? []
  // Fase 14: el gráfico identifica el mes parcial (asterisco + nota al pie)
  const mesParcial = evolution.find((m) => m.parcial) ?? null
  const hasCosts = Boolean(kpis?.ganancia_neta)
  const splitFinancialScale = hasCosts && shouldSplitFinancialScale(evolution)
  const margin = kpis?.margen_utilidad_pct?.valor ?? null
  const health =
    margin === null
      ? null
      : margin >= 25
        ? { text: 'Excelente', tone: 'green' as const }
        : margin >= 10
          ? { text: 'Buena', tone: 'green' as const }
          : margin >= 0
            ? { text: 'Regular', tone: 'gold' as const }
            : { text: 'Crítica', tone: 'coral' as const }

  // Fase 12b §13: el margen mensual viene del backend con el MISMO denominador
  // pareado que el KPI global — derivarlo aquí como utilidad/ingresos volvía a
  // subestimarlo cuando parte de las ventas no tiene costo.
  const sparkOf = (key: 'ingresos' | 'gastos' | 'utilidad' | 'margen') =>
    evolution.map((m) => ({
      v:
        key === 'margen'
          ? (m.margen_pareado_pct ?? null)
          : ((m[key] ?? null) as number | null),
    }))

  // Fase 8: los KPIs se adaptan al archivo. Con columna de costos se muestran
  // ganancia/margen/flujo; sin ella, indicadores REALES de ingresos en vez de
  // tres tarjetas vacías con "—".
  const kpiCards = kpis
    ? hasCosts
      ? [
          {
            label: 'Ingresos Totales',
            icon: Wallet,
            color: CHART.ingresos,
            value: formatCLP(kpis.ingresos_totales.valor),
            variation: <Variation pct={kpis.ingresos_totales.variacion_pct} suffix="vs mes anterior" />,
            spark: sparkOf('ingresos'),
          },
          {
            label: 'Costo Conocido',
            icon: Coins,
            color: CHART.gastos,
            value: kpis.gastos_totales ? formatCLP(kpis.gastos_totales.valor) : '—',
            variation: kpis.base_costos ? (
              <p
                className="text-xs text-navy/40"
                title="La utilidad no usa ventas sin costo ni costos sin ingreso. No se consideran costo cero."
              >
                {formatNumber(kpis.base_costos.filas_con_costo)} registros con costo;{' '}
                {formatNumber(kpis.base_costos.filas_pareadas)} pareados para utilidad
              </p>
            ) : null,
            spark: sparkOf('gastos'),
          },
          {
            label: 'Utilidad Bruta',
            icon: BarChart3,
            color: CHART.gastos,
            value: kpis.ganancia_neta ? formatCLP(kpis.ganancia_neta.valor) : '—',
            variation: kpis.ganancia_neta ? (
              <Variation pct={kpis.ganancia_neta.variacion_pct} suffix="vs mes anterior" />
            ) : (
              <p className="text-xs text-navy/40">Requiere columna de costos</p>
            ),
            spark: sparkOf('utilidad'),
          },
          {
            label: 'Margen Bruto',
            icon: Percent,
            color: CHART.utilidad,
            value: margin !== null ? `${formatNumber(margin)}%` : '—',
            variation: kpis.margen_utilidad_pct ? (
              <Variation pct={kpis.margen_utilidad_pct.variacion_puntos} suffix="vs mes anterior" points />
            ) : (
              <p className="text-xs text-navy/40">Requiere columna de costos</p>
            ),
            spark: sparkOf('margen'),
          },
          {
            // Fase 12b §15: "Resultado del Periodo" era EXACTAMENTE la misma
            // Utilidad Bruta repetida. Esta tarjeta ahora muestra la cobertura
            // de costos: cuánto de la venta respalda el margen que estás viendo.
            label: 'Cobertura de Costos',
            icon: TrendingUp,
            color: CHART.flujo,
            value: kpis.cobertura_costos ? `${formatNumber(kpis.cobertura_costos.pct)}%` : '—',
            variation: kpis.cobertura_costos ? (
              <p className="text-xs text-navy/40">
                {formatNumber(kpis.cobertura_costos.filas_con_ingreso_y_costo)} de{' '}
                {formatNumber(kpis.cobertura_costos.filas_con_ingreso)} ventas con costo
              </p>
            ) : (
              <p className="text-xs text-navy/40">Requiere columna de costos</p>
            ),
            spark: evolution.map((m) => ({ v: m.cobertura_costos_pct ?? null })),
          },
        ]
      : [
          {
            label: 'Ingresos Totales',
            icon: Wallet,
            color: CHART.ingresos,
            value: formatCLP(kpis.ingresos_totales.valor),
            variation: <Variation pct={kpis.ingresos_totales.variacion_pct} suffix="vs mes anterior" />,
            spark: sparkOf('ingresos'),
          },
          {
            label: 'Ticket Promedio',
            icon: Coins,
            color: CHART.utilidad,
            value: formatCLP(kpis.ticket_promedio),
            variation: <p className="text-xs text-navy/40">por registro con monto</p>,
            spark: sparkOf('ingresos'),
          },
          {
            label: 'Registros',
            icon: Receipt,
            color: CHART.gastos,
            value: formatNumber(kpis.transacciones),
            variation: <p className="text-xs text-navy/40">filas en el periodo</p>,
            spark: sparkOf('ingresos'),
          },
          {
            label: 'Tendencia Mensual',
            icon: TrendingUp,
            color: CHART.flujo,
            value: metrics?.proyeccion
              ? `${metrics.proyeccion.crecimiento_pct >= 0 ? '+' : ''}${formatNumber(metrics.proyeccion.crecimiento_pct)}%`
              : '—',
            variation: <p className="text-xs text-navy/40">crecimiento promedio</p>,
            spark: sparkOf('ingresos'),
          },
        ]
    : []

  const canal = metrics?.ventas_por_canal ?? []
  const canalLabel = metrics?.agrupado_por_canal === 'sucursal' ? 'Sucursal' : 'Canal'
  const canalTotal = canal.reduce((sum, item) => sum + item.ingresos, 0)
  // El backend entrega hasta 12 productos (Explorar los usa); el Resumen
  // muestra el top 5 clásico.
  const topProducts = (metrics?.top_productos ?? []).slice(0, 5)
  const maxProduct = topProducts[0]?.ingresos ?? 1
  // Solo en una hoja de ventas (sin costos relacionados) las columnas de costo,
  // utilidad y margen salen todas "—": no aportan y las ocultamos.
  const categoriaConCostos = (metrics?.por_categoria ?? []).some((row) => row.costo != null)
  // Sin esas 3 columnas la tabla queda con huecos: una barra de participación
  // que se estira llena el ancho con algo útil.
  const maxCategoria = Math.max(...(metrics?.por_categoria ?? []).map((row) => row.ingresos), 1)

  return (
    <>
      <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <PageHeader
          className="!mb-0"
          title={demo.active ? 'Demo — Comercial Andes SpA' : firstName ? `Bienvenido, ${firstName} 👋` : 'Bienvenido 👋'}
          subtitle={
            demo.active
              ? 'Datos ficticios de ejemplo — así se ve tu dashboard con datos ficticios realistas de un negocio.'
              : `Este es el resumen general de tu negocio — ${period.label.toLowerCase()}${
                  // Fase 13 (P0.4): lo decide el BACKEND con los datos (no el reloj):
                  // si el mes está incompleto, la variación compara días equivalentes.
                  metrics?.periodo.mes_parcial
                    ? ' (mes incompleto: variación por días equivalentes)'
                    : ''
                }.`
          }
        />
        <Link
          to="/estandarizacion"
          className="inline-flex w-full shrink-0 items-center justify-center gap-2 rounded-lg bg-gold px-4 py-2.5 text-sm font-semibold text-navy-deep transition-colors hover:bg-gold/90 sm:w-auto"
        >
          <Upload className="h-4 w-4" /> Importar datos
        </Link>
      </div>

      <ActiveSheetSelector />

      {error && (
        <div className="mb-6 flex flex-wrap items-start gap-2 rounded-lg border border-coral/40 bg-coral/10 px-4 py-3 text-sm text-coral">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p className="min-w-0 flex-1">{error}</p>
          <button
            type="button"
            onClick={() => setRetryTick((t) => t + 1)}
            className="shrink-0 rounded-lg border border-coral/40 bg-white px-3 py-1 text-xs font-semibold text-coral transition-colors hover:bg-coral/10"
          >
            Reintentar
          </button>
        </div>
      )}

      {resumeWarning && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-gold/40 bg-gold/10 px-4 py-3 text-sm text-navy/80">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
          <p>{resumeWarning}</p>
        </div>
      )}

      {loading && !metrics ? (
        <div className="flex items-center gap-3 py-20 text-sm text-navy/60">
          <Loader2 className="h-5 w-5 animate-spin text-teal" /> Calculando indicadores...
        </div>
      ) : contentKind === 'mixed_currency' ? (
        /* El bloqueo antecede a todos los perfiles adaptativos. Un catálogo o
           campaña mixta conserva conteos seguros en el contrato, pero no debe
           ocultar que sus costos, precios, inversión y CPC están bloqueados. */
        <EmptyState
          icon={Wallet}
          title="Tu archivo mezcla más de una moneda"
          description="Detectamos montos en monedas distintas: sumarlos produciría totales sin sentido, así que los indicadores monetarios quedan bloqueados. Separa el archivo por moneda (una por archivo) o corrige la columna de montos y vuelve a procesarlo. Las advertencias del motor traen el detalle."
          ctaLabel="Revisar en Limpieza"
          ctaTo="/limpieza"
        />
      ) : metrics?.analisis_negocio ? (
        <BusinessAnalysisPanel analysis={metrics.analisis_negocio} variant="summary" />
      ) : contentKind === 'product_catalog' && metrics?.analisis_productos ? (
        <ProductCatalogSummary analysis={metrics.analisis_productos} variant="summary" />
      ) : contentKind === 'adaptive_profile' && metrics ? (
        <AdaptiveProfileSummary metrics={metrics} variant="summary" />
      ) : contentKind === 'missing_amount' ? (
        /* Fase 11: sin columna de monto el dashboard sería puro $0 — mejor
           decirlo claro y llevar al usuario al mapeo de columnas. */
        <EmptyState
          icon={Wallet}
          title="No detectamos la columna de ventas o monto"
          description="Tu archivo se procesó, pero ninguna columna se reconoció como monto de venta. Asígnala manualmente en el mapeo de columnas de Limpieza y el dashboard se calculará con tus datos."
          ctaLabel="Ir a asignar columnas"
          ctaTo="/limpieza"
          ctaState={{ openMapping: true, highlightRole: 'monto' }}
        />
      ) : metrics && kpis ? (
        <div className={loading ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
          {/* KPIs (con tono suave del color de cada indicador) */}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {kpiCards.map(({ label, icon: Icon, color, value, variation, spark }) => (
              <Card
                key={label}
                className="!p-4"
                style={{ background: `linear-gradient(135deg, ${color}0d, #ffffff 55%)` }}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
                    style={{ background: `${color}1a` }}
                  >
                    <Icon className="h-4 w-4" style={{ color }} />
                  </span>
                  <p className="text-xs font-medium text-navy/55">{label}</p>
                </div>
                <p className="mt-2.5 text-[22px] font-bold leading-tight text-navy">{value}</p>
                <div className="mt-1.5 flex items-end justify-between gap-2">
                  <div className="min-w-0">{variation}</div>
                  <Sparkline data={spark} color={color} />
                </div>
              </Card>
            ))}
          </div>

          {!hasCosts && (
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-teal/25 bg-teal/[0.05] px-4 py-2.5 text-xs text-navy/65">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal" />
              <p>
                {metrics?.dimensiones?.costo
                  ? 'Tu archivo trae una columna de costos, pero ninguna venta tiene su costo asociado en este periodo: la utilidad y el margen no se pueden calcular.'
                  : 'Tu archivo no trae una columna de costos: agrégala (o asígnala en el mapeo de Limpieza) para ver utilidad bruta y margen.'}
              </p>
            </div>
          )}

          {(metrics.duplicados?.conservados ?? 0) > 0 && (
            <div className="mt-4 flex flex-wrap items-start gap-2 rounded-lg border border-gold/40 bg-gold/[0.07] px-4 py-2.5 text-xs text-navy/75">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gold" />
              <p className="min-w-0 flex-1">
                Se detectaron <strong>{formatNumber(metrics.duplicados?.detectados ?? 0)}</strong>{' '}
                duplicados exactos y se conservaron{' '}
                <strong>{formatNumber(metrics.duplicados?.conservados ?? 0)}</strong> porque no
                confirmaste su eliminación. Los totales actuales los incluyen.
              </p>
              <Link
                to="/limpieza?revision=1"
                className="ml-5 inline-flex shrink-0 rounded-md border border-gold/45 bg-white px-2.5 py-1.5 font-semibold text-navy hover:bg-gold/[0.06] sm:ml-0"
              >
                Ver detalle y ajustar
              </Link>
            </div>
          )}

          {/* Advertencias de exactitud (Fase 10): moneda distinta/mezclada y
              cobertura parcial de costos — el usuario debe saberlo SIEMPRE. */}
          {metrics.advertencias.filter((a) => !a.startsWith('No se detectó')).length > 0 && (
            <div className="mt-4 space-y-2">
              {metrics.advertencias
                .filter((a) => !a.startsWith('No se detectó'))
                .slice(0, 3)
                .map((aviso) => (
                  <div
                    key={aviso}
                    className="flex items-start gap-2 rounded-lg border border-gold/40 bg-gold/[0.07] px-4 py-2.5 text-xs text-navy/75"
                  >
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gold" />
                    <p>{aviso}</p>
                  </div>
                ))}
            </div>
          )}

          {/* En escritorio, cada columna avanza con su propia altura: una
              tarjeta alta a la derecha no reserva espacio vacío a la izquierda.
              En móvil, `contents` + `order` conserva el orden de lectura. */}
          <div className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div className="contents xl:block xl:space-y-6">
              <Card className="order-1 min-w-0">
              <h2 className="text-base font-semibold text-navy">
                {hasCosts ? 'Evolución de Ingresos, Gastos y Utilidad' : 'Ingresos por mes'}
              </h2>
              {(period.from || period.to) && (
                <p className="mt-0.5 text-xs text-navy/45">
                  Contexto histórico completo (los KPIs de arriba corresponden al periodo
                  seleccionado).
                </p>
              )}
              {splitFinancialScale ? (
                <div className="mt-4 space-y-4">
                  <div className="flex items-start gap-2 rounded-lg border border-gold/35 bg-gold/[0.07] px-3 py-2 text-xs text-navy/70">
                    <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gold" />
                    <p>Separamos las escalas porque costos o utilidad tienen una magnitud muy distinta. Así los ingresos no quedan visualmente planos; los valores originales no se modifican.</p>
                  </div>
                  <div className="grid gap-4 2xl:grid-cols-2">
                    <div>
                      <p className="mb-2 text-xs font-semibold text-navy/65">Ingresos</p>
                      <div className="h-56"><FinancialLineChart evolution={evolution} mesParcial={mesParcial?.mes} series={['ingresos']} showAverage /></div>
                    </div>
                    <div>
                      <p className="mb-2 text-xs font-semibold text-navy/65">Costos y utilidad</p>
                      <div className="h-56"><FinancialLineChart evolution={evolution} mesParcial={mesParcial?.mes} series={['gastos', 'utilidad']} /></div>
                    </div>
                  </div>
                </div>
              ) : hasCosts ? (
                <div className="mt-4 h-72">
                  <FinancialLineChart
                    evolution={evolution}
                    mesParcial={mesParcial?.mes}
                    series={['ingresos', 'gastos', 'utilidad']}
                    showAverage
                  />
                </div>
              ) : (
                /* Hoja de ventas sin costos: un solo indicador (ingresos) se lee
                   mejor como barras por mes que como una línea suelta. */
                <div className="mt-4 h-72">
                  <MonthlyIncomeBars evolution={evolution} mesParcial={mesParcial?.mes} />
                </div>
              )}
              {hasCosts && (
                <div className="mt-2 flex flex-wrap gap-4 text-xs text-navy/70">
                  {[
                    { name: 'Ingresos', color: CHART.ingresos },
                    { name: 'Gastos', color: CHART.gastos },
                    { name: 'Utilidad', color: CHART.utilidad },
                  ].map((s) => (
                    <span key={s.name} className="flex items-center gap-1.5">
                      <span className="h-0.5 w-4 rounded" style={{ background: s.color }} />
                      {s.name}
                    </span>
                  ))}
                </div>
              )}
              {mesParcial && (
                /* Fase 14b: el copy declara el HECHO (último registro), no la
                   causa — el archivo no permite saber si faltan datos o
                   simplemente no hubo ventas después de ese día. */
                <p className="mt-1.5 text-[11px] text-navy/45">
                  * {formatMonthShort(mesParcial.mes)}: último registro disponible el día{' '}
                  {mesParcial.cobertura_hasta_dia} de {mesParcial.dias_del_mes} — para no
                  comparar coberturas distintas, la proyección y las alertas no lo usan
                  como mes completo.
                </p>
              )}
              </Card>

              {(metrics.por_categoria ?? []).length > 0 && (
              <Card className="order-3 min-w-0">
              <h2 className="text-base font-semibold text-navy">Análisis por Categoría</h2>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-navy/10 text-left text-xs font-semibold uppercase tracking-wide text-navy/50">
                      <th className="whitespace-nowrap pb-2 pr-4">Categoría</th>
                      <th className="whitespace-nowrap pb-2 pr-4 text-right">Ingresos</th>
                      {/* Fase 14b: participación BRUTA — distribución real que suma 100% */}
                      <th className="whitespace-nowrap pb-2 pr-4 text-right">% Ventas brutas</th>
                      {categoriaConCostos ? (
                        <>
                          <th className="whitespace-nowrap pb-2 pr-4 text-right">Costo asociado</th>
                          <th className="whitespace-nowrap pb-2 pr-4 text-right">Utilidad</th>
                          <th className="pb-2">Margen</th>
                        </>
                      ) : (
                        <th className="w-full pb-2" aria-label="Participación" />
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {(metrics.por_categoria ?? []).map((row) => (
                      <tr key={row.nombre} className="border-b border-navy/5">
                        <td className="py-2.5 pr-4 font-medium text-navy">{row.nombre}</td>
                        <td className="py-2.5 pr-4 text-right text-navy/75">{formatCLP(row.ingresos)}</td>
                        <td className="whitespace-nowrap py-2.5 pr-4 text-right text-navy/75">
                          {formatNumber(row.participacion_bruta_pct ?? row.porcentaje)}%
                        </td>
                        {categoriaConCostos ? (
                          <>
                            <td className="py-2.5 pr-4 text-right text-navy/75">
                              {row.costo != null ? formatCLP(row.costo) : '—'}
                            </td>
                            <td className="py-2.5 pr-4 text-right text-navy/75">
                              {row.utilidad != null ? formatCLP(row.utilidad) : '—'}
                            </td>
                            <td className="py-2.5">
                              {row.margen_pct !== undefined && row.margen_pct !== null ? (
                                <span className="flex items-center gap-2">
                                  <span className="text-navy/75">{formatNumber(row.margen_pct)}%</span>
                                  <span className="h-1.5 w-16 overflow-hidden rounded-full bg-navy/10">
                                    <span
                                      className="block h-full rounded-full"
                                      style={{
                                        width: `${Math.min(Math.max(row.margen_pct, 0), 100)}%`,
                                        background:
                                          row.margen_pct >= 30
                                            ? CHART.utilidad
                                            : row.margen_pct >= 15
                                              ? CHART.gastos
                                              : CHART.alerta,
                                      }}
                                    />
                                  </span>
                                </span>
                              ) : (
                                '—'
                              )}
                            </td>
                          </>
                        ) : (
                          <td className="w-full py-2.5 pl-2">
                            <span className="block h-1.5 w-full overflow-hidden rounded-full bg-navy/10">
                              <span
                                className="block h-full rounded-full"
                                style={{
                                  width: `${(row.ingresos / maxCategoria) * 100}%`,
                                  background: CHART.ingresos,
                                }}
                              />
                            </span>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              </Card>
              )}
            </div>

            {/* `@container`: las columnas responden al ANCHO REAL de este bloque
                y no al de la ventana, así el panel de IA abierto no lo colapsa.
                Con un número de columnas CONOCIDO (2 en @2xl, 3 en @5xl) la
                última card se estira para no dejar celdas vacías en la última
                fila. El rango de 2 columnas se acota con @max-5xl: si no, su
                regla `odd` se filtraría al modo de 3 y estiraría de más. */}
            <div className="order-5 @container xl:order-last xl:col-span-2">
              <div
                data-testid="summary-compact-flow"
                className="grid grid-cols-1 gap-6 @2xl:grid-cols-2 @5xl:grid-cols-3 @2xl:@max-5xl:[&>*:last-child:nth-child(odd)]:col-span-2 @5xl:[&>*:last-child:nth-child(3n+1)]:col-span-3 @5xl:[&>*:last-child:nth-child(3n+2)]:col-span-2"
              >
                  {canal.length > 0 && (
                  <Card className="flex h-full min-w-0 flex-col">
                    <h2 className="text-base font-semibold text-navy">Ventas por {canalLabel}</h2>
                    <div className="mt-2 flex flex-1 flex-col items-center justify-center gap-3">
                      <div className="relative h-44 w-44 shrink-0">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={canal}
                              dataKey="ingresos"
                              nameKey="nombre"
                              innerRadius="62%"
                              outerRadius="95%"
                              stroke="#ffffff"
                              strokeWidth={2}
                              isAnimationActive={false}
                            >
                              {canal.map((entry, index) => (
                                <Cell key={entry.nombre} fill={CATEGORICAL[index % CATEGORICAL.length]} />
                              ))}
                            </Pie>
                            <Tooltip content={<ChartTooltip />} />
                          </PieChart>
                        </ResponsiveContainer>
                        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                          <p className="text-sm font-bold text-navy">{formatCLPCompact(canalTotal)}</p>
                          <p className="text-[10px] text-navy/50">Total</p>
                        </div>
                      </div>
                      <ul className="w-full space-y-1.5">
                        {canal.map((entry, index) => (
                          <li key={entry.nombre} className="flex items-center justify-between gap-2 text-xs">
                            <span className="flex min-w-0 items-center gap-1.5 text-navy/75">
                              <span
                                className="h-2.5 w-2.5 shrink-0 rounded-full"
                                style={{ background: CATEGORICAL[index % CATEGORICAL.length] }}
                              />
                              <span className="truncate" title={entry.nombre}>
                                {entry.nombre}
                              </span>
                            </span>
                            <span className="shrink-0 font-semibold text-navy">
                              {formatCLPCompact(entry.ingresos)}
                              <span className="ml-1.5 font-normal text-navy/45">
                              {formatNumber(entry.participacion_neta_pct ?? entry.porcentaje)}%
                              </span>
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </Card>
                  )}

                  {topProducts.length > 0 && (
                  <Card className="flex h-full min-w-0 flex-col">
                    <h2 className="text-base font-semibold text-navy">Top Productos / Servicios</h2>
                    {/* flex-1 + reparto uniforme: los productos ocupan el alto
                        sobrante en vez de dejar un hueco al pie de la card. */}
                    <ul className="mt-4 flex flex-1 flex-col justify-around gap-3">
                      {topProducts.map((product) => (
                        <li key={product.nombre}>
                          <div className="flex items-center justify-between gap-2 text-sm">
                            <span className="truncate text-navy/80">{product.nombre}</span>
                            <span className="shrink-0 font-semibold text-navy">
                              {formatCLP(product.ingresos)}
                              <span className="ml-2 text-xs font-normal text-navy/45">
                                {formatNumber(product.participacion_neta_pct ?? product.porcentaje)}%
                              </span>
                            </span>
                          </div>
                          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-navy/10">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${(product.ingresos / maxProduct) * 100}%`,
                                background: CHART.ingresos,
                              }}
                            />
                          </div>
                        </li>
                      ))}
                    </ul>
                  </Card>
                  )}

                  <Card className="flex h-full min-w-0 flex-col">
                    {/* Fase 12b §20: es una EXTRAPOLACIÓN del promedio observado, no
                        una predicción — el copy no debe prometer más que el método. */}
                    <h2 className="text-base font-semibold text-navy">
                      Extrapolación simple (3 meses)
                    </h2>
                    {metrics.proyeccion ? (
                      <>
                        <p className="mt-2 text-sm text-navy/60">
                          Si se mantiene el crecimiento promedio observado
                        </p>
                        <p className="text-3xl font-bold text-navy">
                          {metrics.proyeccion.crecimiento_pct >= 0 ? '+' : ''}
                          {formatNumber(metrics.proyeccion.crecimiento_pct)}%
                        </p>
                        <p className="text-xs text-navy/50">mensual promedio</p>
                        <div className="mt-3 flex-1" style={{ minHeight: 96 }}>
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart
                              data={[
                                ...evolution.map((m) => ({ mes: m.mes, real: m.ingresos })),
                                ...metrics.proyeccion.meses.map((m) => ({
                                  mes: m.mes,
                                  proyectado: m.ingresos,
                                })),
                              ]}
                              margin={{ top: 6, right: 8, bottom: 0, left: 8 }}
                            >
                              <XAxis
                                dataKey="mes"
                                tickFormatter={formatMonthShort}
                                tick={{ fill: AXIS_INK, fontSize: 10 }}
                                axisLine={{ stroke: GRID_STROKE }}
                                tickLine={false}
                              />
                              <Tooltip content={<ChartTooltip />} />
                              <Line
                                type="monotone"
                                dataKey="real"
                                name="Real"
                                stroke={CHART.ingresos}
                                strokeWidth={2}
                                dot={false}
                              />
                              <Line
                                type="monotone"
                                dataKey="proyectado"
                                name="Proyectado"
                                stroke={CHART.gastos}
                                strokeWidth={2}
                                strokeDasharray="5 4"
                                dot={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                        <p className="mt-auto pt-3 text-[11px] text-navy/45">
                          Extrapolación del crecimiento promedio de {evolution.length} mes(es) de
                          historia — no considera estacionalidad ni meses incompletos. Línea
                          punteada = extrapolación.
                        </p>
                      </>
                    ) : (
                      <p className="mt-4 text-sm text-navy/50">
                        Se necesitan al menos 2 meses de historia para proyectar tus ingresos.
                      </p>
                    )}
                  </Card>

              {/* Fase 18: agrupaciones flexibles — ventas por sucursal, región,
                  zona u otras columnas categóricas del archivo (incluidas las
                  enriquecidas por "Relacionar otras hojas"). */}
                  {/* Sin div envolvente: cada card ES el ítem de la grilla, así
                      `h-full` iguala alturas y el conteo nth-child es correcto. */}
                  {(metrics.agrupaciones_flexibles ?? []).map((agrupacion) => (
                    <FlexibleGroupCard key={agrupacion.columna} agrupacion={agrupacion} />
                  ))}
              </div>
            </div>

            <div className="contents xl:block xl:space-y-6">
              <Card className="order-2">
              <h2 className="text-base font-semibold text-navy">Indicadores Clave</h2>
              <p className="mt-0.5 text-xs text-navy/50">Calculados de tus datos reales.</p>
              <ul className="mt-3 divide-y divide-navy/5">
                {buildOperationalIndicators(metrics).map(({ label, value, hint }) => (
                  <li key={label} className="flex items-center justify-between gap-2 py-2.5 text-sm">
                    <span className="text-navy/70">{label}</span>
                    <span className="text-right">
                      <span className="font-semibold text-navy">{value}</span>
                      {hint && <span className="block text-[10px] text-navy/40">{hint}</span>}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 rounded-lg bg-navy/[0.04] px-3 py-2 text-[11px] leading-relaxed text-navy/50">
                ROA, ROE, liquidez y prueba ácida se habilitarán cuando conectes los datos
                de balance de tu negocio.
              </p>
              </Card>

              <Card className="order-4">
              <h2 className="text-base font-semibold text-navy">Estado Financiero</h2>
              <ul className="mt-4 divide-y divide-navy/5 text-sm">
                {['Activos Totales', 'Pasivos Totales', 'Patrimonio', 'Capital de Trabajo'].map(
                  (label) => (
                    <li key={label} className="flex items-center justify-between py-2.5">
                      <span className="text-navy/70">{label}</span>
                      <span className="font-semibold text-navy/35">—</span>
                    </li>
                  ),
                )}
              </ul>
              {health && (
                <div className="mt-4 flex items-center justify-between gap-3 rounded-lg border border-navy/10 bg-work px-4 py-3">
                  <div className="flex items-center gap-2">
                    <HeartPulse className="h-4.5 w-4.5 text-teal" />
                    <div>
                      <p className="text-sm font-semibold text-navy">Salud Financiera</p>
                      <p className="text-[11px] text-navy/50">
                        Según el margen del periodo — referencia general; depende del rubro
                      </p>
                    </div>
                  </div>
                  <Badge tone={health.tone}>{health.text}</Badge>
                </div>
              )}
              <p className="mt-3 text-[11px] leading-relaxed text-navy/45">
                Activos, pasivos y patrimonio se habilitan al conectar tus datos de balance.
              </p>
              </Card>
            </div>
          </div>

        </div>
      ) : null}
    </>
  )
}

function FinancialLineChart({
  evolution,
  mesParcial,
  series,
  showAverage = false,
}: {
  evolution: MetricsResult['evolucion_mensual']
  mesParcial?: string
  series: Array<'ingresos' | 'gastos' | 'utilidad'>
  showAverage?: boolean
}) {
  const config = {
    ingresos: { name: 'Ingresos', color: CHART.ingresos },
    gastos: { name: 'Gastos', color: CHART.gastos },
    utilidad: { name: 'Utilidad', color: CHART.utilidad },
  } as const
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={evolution} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
        <CartesianGrid stroke={GRID_STROKE} vertical={false} />
        <XAxis
          dataKey="mes"
          tickFormatter={(value: string) => `${formatMonthShort(value)}${value === mesParcial ? '*' : ''}`}
          tick={{ fill: AXIS_INK, fontSize: 11 }}
          axisLine={{ stroke: GRID_STROKE }}
          tickLine={false}
        />
        <YAxis tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} width={62} />
        <Tooltip content={<ChartTooltip />} />
        {showAverage && evolution.length >= 2 && (
          <ReferenceLine
            y={evolution.reduce((sum, row) => sum + row.ingresos, 0) / evolution.length}
            stroke={AXIS_INK}
            strokeDasharray="6 4"
            strokeOpacity={0.55}
            label={{ value: 'promedio', position: 'insideTopRight', fill: AXIS_INK, fontSize: 10 }}
          />
        )}
        {series.map((key) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            name={config[key].name}
            stroke={config[key].color}
            strokeWidth={2.5}
            connectNulls={false}
            dot={{ r: 3, strokeWidth: 0, fill: config[key].color }}
            activeDot={{ r: 5 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

/** Ingresos por mes en barras — para hojas de venta sin costos, donde la
 * evolución tiene un solo indicador y una línea suelta se lee peor. */
function MonthlyIncomeBars({
  evolution,
  mesParcial,
}: {
  evolution: MetricsResult['evolucion_mensual']
  mesParcial?: string
}) {
  const promedio =
    evolution.length >= 2
      ? evolution.reduce((sum, row) => sum + row.ingresos, 0) / evolution.length
      : null
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={evolution} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
        <CartesianGrid stroke={GRID_STROKE} vertical={false} />
        <XAxis
          dataKey="mes"
          tickFormatter={(value: string) => `${formatMonthShort(value)}${value === mesParcial ? '*' : ''}`}
          tick={{ fill: AXIS_INK, fontSize: 11 }}
          axisLine={{ stroke: GRID_STROKE }}
          tickLine={false}
        />
        <YAxis tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} width={62} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: `${CHART.ingresos}14` }} />
        {promedio != null && (
          <ReferenceLine
            y={promedio}
            stroke={AXIS_INK}
            strokeDasharray="6 4"
            strokeOpacity={0.55}
            label={{ value: 'promedio', position: 'insideTopRight', fill: AXIS_INK, fontSize: 10 }}
          />
        )}
        <Bar dataKey="ingresos" name="Ingresos" fill={CHART.ingresos} radius={[4, 4, 0, 0]} maxBarSize={48} isAnimationActive={false}>
          {evolution.map((row) => (
            <Cell key={row.mes} fill={row.mes === mesParcial ? `${CHART.ingresos}99` : CHART.ingresos} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Fase 18: gráfico de una agrupación flexible (ventas por sucursal/región…). */
function FlexibleGroupCard({
  agrupacion,
}: {
  agrupacion: NonNullable<MetricsResult['agrupaciones_flexibles']>[number]
}) {
  const rows = agrupacion.grupos.slice(0, 10).map((grupo) => ({
    ...grupo,
    // El eje Y reserva 150px: a 11px de fuente entran ~22 caracteres en UNA
    // línea. Truncar a 20 evita que Recharts parta la etiqueta en dos
    // ("Fuera de / rango", "Nota de / Crédito") o la recorte contra el borde.
    etiqueta: truncateLabel(grupo.nombre, 20),
  }))
  const chartColor = chartColorForKey(agrupacion.columna)
  const useDonut = rows.length >= 2 && rows.length <= 5 && rows.every((row) => row.ingresos >= 0)
  const total = rows.reduce((sum, row) => sum + row.ingresos, 0)
  const hasNegative = rows.some((row) => row.ingresos < 0)
  return (
    <Card className="@container flex h-full min-w-0 flex-col" style={{ background: `linear-gradient(145deg, ${chartColor}0b, #ffffff 42%)` }}>
      <div className="flex items-center gap-2">
        <span className="h-3 w-3 rounded-full" style={{ background: chartColor }} />
        <h2 className="text-base font-semibold text-navy">Ventas por {agrupacion.columna}</h2>
      </div>
      <p className="mt-1 text-xs text-navy/55">
        Ingresos netos según la columna «{agrupacion.columna}» de tu archivo
        {agrupacion.grupos_totales > rows.length
          ? ` (top ${rows.length} de ${agrupacion.grupos_totales} valores)`
          : ''}
        .
      </p>
      {agrupacion.fuera_de_rango && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-gold/35 bg-gold/[0.08] px-3 py-2 text-xs text-navy/70">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-gold" />
          <span className="min-w-0 flex-1">
            <strong>{formatNumber(agrupacion.fuera_de_rango.filas)}</strong> filas están fuera de 0–100%
            {' · '}monto asociado: <strong>{formatCLP(agrupacion.fuera_de_rango.monto_asociado)}</strong>.
          </span>
          <Link to="/limpieza?revision=1" className="font-semibold text-teal hover:underline">
            Revisar detalle
          </Link>
        </div>
      )}
      {useDonut ? (
        /* El layout depende del ancho de LA CARD (@container), no de la
           ventana: angosta → dona arriba y leyenda debajo en una columna;
           ancha (cuando ocupa la fila completa) → dona a la izquierda y
           leyenda en DOS columnas que llenan el ancho, en vez de una dona
           chica al centro con los montos pegados a los bordes. */
        <div className="mt-4 flex flex-1 flex-col items-center justify-center gap-4 @2xl:flex-row @2xl:gap-8">
          <div className="relative h-40 w-40 shrink-0 @2xl:h-48 @2xl:w-48">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={rows} dataKey="ingresos" nameKey="etiqueta" innerRadius="60%" outerRadius="92%" stroke="#ffffff" strokeWidth={2} isAnimationActive={false}>
                  {rows.map((row, index) => <Cell key={row.nombre} fill={CATEGORICAL[index % CATEGORICAL.length]} />)}
                </Pie>
                <Tooltip formatter={(value) => formatCLP(Number(value))} />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <p className="text-sm font-bold text-navy">{formatCLPCompact(total)}</p>
              <p className="text-[10px] text-navy/50">Total</p>
            </div>
          </div>
          {/* Más columnas a medida que la card crece: así cada fila queda
              angosta y el monto no se despega del nombre. */}
          <ul className="w-full space-y-1.5 @2xl:grid @2xl:flex-1 @2xl:grid-cols-2 @2xl:gap-x-8 @2xl:gap-y-2 @2xl:space-y-0 @4xl:grid-cols-3">
            {rows.map((row, index) => (
              <li key={row.nombre} className="flex items-center justify-between gap-2 text-xs">
                <span className="flex min-w-0 items-center gap-1.5 text-navy/75">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: CATEGORICAL[index % CATEGORICAL.length] }} />
                  <span className="truncate" title={row.nombre}>{row.nombre}</span>
                </span>
                <span className="shrink-0 whitespace-nowrap font-semibold text-navy">
                  {formatCLPCompact(row.ingresos)}
                  <span className="ml-1.5 font-normal text-navy/45">
                    {formatNumber(row.participacion_neta_pct ?? row.porcentaje)}%
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        /* flex-1: el gráfico ABSORBE el alto sobrante de la card en vez de
           quedarse chico y dejar un hueco antes de la nota. El minHeight
           conserva el piso necesario para que las barras se lean. */
        <div className="mt-4 flex-1" style={{ minHeight: Math.max(rows.length * 34 + 44, 150) }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
              <XAxis type="number" tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="etiqueta" width={150} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
              <ReferenceLine x={0} stroke={AXIS_INK} strokeOpacity={0.45} />
              <Tooltip formatter={(value) => formatCLP(Number(value))} />
              <Bar dataKey="ingresos" name="Ingresos" fill={chartColor} radius={[0, 4, 4, 0]}>
                {rows.map((row) => <Cell key={row.nombre} fill={row.ingresos < 0 ? CHART.alerta : chartColor} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {hasNegative && (
        /* Explica por qué una barra puede ir a la izquierda del cero — p. ej. una
           Nota de Crédito, que resta ventas en vez de sumarlas. */
        <p className="mt-auto flex items-start gap-1.5 pt-3 text-[11px] leading-relaxed text-navy/50">
          <Info className="mt-0.5 h-3 w-3 shrink-0 text-coral" />
          <span>
            Los valores en <span className="font-semibold text-coral">coral (negativos)</span> restan ingresos:
            son notas de crédito, devoluciones o anulaciones que reducen la venta neta. No es un error.
          </span>
        </p>
      )}
    </Card>
  )
}
