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
import { useAuth } from '../auth/AuthContext'
import { monthPeriod, useDataset } from '../data/DatasetContext'
import { apiPost, buildDatasetForm, ApiError } from '../lib/api'
import { AXIS_INK, CATEGORICAL, CHART, GRID_STROKE, formatCLPCompact, formatMonthShort } from '../lib/charts'
import { formatCLP, formatNumber, setActiveCurrency } from '../lib/format'
import type { MetricsResult } from '../lib/types'

/** Indicadores operativos del negocio, calculados de los datos reales del
 * archivo (los ratios de balance —ROA, ROE, liquidez— requieren conectar
 * datos de balance y quedan como nota hasta entonces). */
function buildOperationalIndicators(m: MetricsResult): Array<{ label: string; value: string; hint?: string }> {
  const kpis = m.kpis
  const evo = m.evolucion_mensual
  const items: Array<{ label: string; value: string; hint?: string }> = []

  items.push({ label: 'Ticket promedio', value: formatCLP(kpis.ticket_promedio), hint: 'por venta' })
  items.push({ label: 'Transacciones', value: formatNumber(kpis.transacciones), hint: 'en el periodo' })
  if (kpis.unidades_totales != null) {
    items.push({ label: 'Unidades vendidas', value: formatNumber(kpis.unidades_totales) })
  }
  if (evo.length >= 2) {
    const best = evo.reduce((a, b) => (b.ingresos > a.ingresos ? b : a))
    items.push({
      label: 'Mejor mes',
      value: formatMonthShort(best.mes),
      hint: formatCLP(best.ingresos),
    })
    const first = evo[0]
    if (first.ingresos > 0) {
      const totalGrowth = ((evo[evo.length - 1].ingresos - first.ingresos) / first.ingresos) * 100
      items.push({
        label: 'Crecimiento del periodo',
        value: `${totalGrowth >= 0 ? '+' : ''}${formatNumber(Math.round(totalGrowth * 10) / 10)}%`,
        hint: `${formatMonthShort(first.mes)} → ${formatMonthShort(evo[evo.length - 1].mes)}`,
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
  return items.slice(0, 7)
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
  const { file, datasetId, storagePath, cleaning, uploadedAt, period, setPeriod, setMonthsAvailable, setMetrics: setContextMetrics, mappingOverride, sheet } = useDataset()
  const [metrics, setMetrics] = useState<MetricsResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Fase 11 §9.3: tras un fallo (timeout, red) el usuario puede reintentar sin
  // recargar la página — el botón incrementa retryTick y el efecto vuelve a correr.
  const [retryTick, setRetryTick] = useState(0)
  const defaultPeriodSet = useRef(false)
  const lastFetchKey = useRef<string | null>(null)
  const lastDatasetKey = useRef<string | null>(null)

  const firstName =
    ((user?.user_metadata?.full_name as string | undefined) ?? '').trim().split(' ')[0] || null
  const ready = Boolean(file && cleaning)
  const resumeWarning =
    typeof (location.state as { resumeWarning?: unknown } | null)?.resumeWarning === 'string'
      ? ((location.state as { resumeWarning: string }).resumeWarning)
      : null

  useEffect(() => {
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
    const key = `${datasetKey}|${period.from}|${period.to}|${sheet ?? ''}|${JSON.stringify(mappingOverride ?? {})}|${retryTick}`
    if (lastFetchKey.current === key) return
    lastFetchKey.current = key
    setLoading(true)
    setError(null)
    const fields: Record<string, string> = {}
    if (mappingOverride) fields.mapping = JSON.stringify(mappingOverride)
    if (sheet) fields.sheet = sheet
    if (period.from) fields.date_from = period.from
    if (period.to) fields.date_to = period.to
    apiPost<MetricsResult>('/metrics', buildDatasetForm(file, storagePath, fields))
      .then((result) => {
        setMetrics(result)
        setActiveCurrency(result.moneda)
        // El contexto compartido (Alertas/Reportes/IA) solo cachea métricas
        // del periodo COMPLETO — jamás el mes filtrado del Resumen (Fase 10 §5).
        if (!period.from && !period.to) setContextMetrics(result)
        const months = result.periodo.meses_disponibles
        setMonthsAvailable(months)
        // Al entrar por primera vez, seleccionar el último mes con datos
        // (así las variaciones "vs periodo anterior" tienen sentido).
        if (!defaultPeriodSet.current && months.length > 1 && !period.from) {
          defaultPeriodSet.current = true
          setPeriod(monthPeriod(months[months.length - 1]))
        }
      })
      .catch((err) => {
        // Si falla, la clave se anula para que el próximo intento sí ejecute
        // (antes quedaba "marcada como hecha" y la página se veía vacía para siempre).
        lastFetchKey.current = null
        setError(err instanceof ApiError ? err.message : 'No se pudieron calcular las métricas.')
      })
      .finally(() => setLoading(false))
  }, [file, datasetId, storagePath, cleaning, uploadedAt, period, sheet, mappingOverride, retryTick, setMonthsAvailable, setPeriod])

  if (!ready) {
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
        />
      </>
    )
  }

  const kpis = metrics?.kpis
  const evolution = metrics?.evolucion_mensual ?? []
  const hasCosts = Boolean(kpis?.ganancia_neta)
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

  const sparkOf = (key: 'ingresos' | 'gastos' | 'utilidad' | 'margen') =>
    evolution.map((m) => ({
      v:
        key === 'margen'
          ? m.utilidad !== undefined && m.ingresos
            ? (m.utilidad / m.ingresos) * 100
            : null
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
            label: 'Resultado del Periodo',
            icon: TrendingUp,
            color: CHART.flujo,
            value: kpis.flujo_caja ? formatCLP(kpis.flujo_caja.valor) : '—',
            variation: kpis.flujo_caja ? (
              <Variation pct={kpis.flujo_caja.variacion_pct} suffix="vs mes anterior" />
            ) : (
              <p className="text-xs text-navy/40">Requiere columna de costos</p>
            ),
            spark: sparkOf('utilidad'),
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
            variation: <p className="text-xs text-navy/40">por transacción</p>,
            spark: sparkOf('ingresos'),
          },
          {
            label: 'Transacciones',
            icon: Receipt,
            color: CHART.gastos,
            value: formatNumber(kpis.transacciones),
            variation: <p className="text-xs text-navy/40">en el periodo</p>,
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
  const topProducts = metrics?.top_productos ?? []
  const maxProduct = topProducts[0]?.ingresos ?? 1

  return (
    <>
      <div className="flex items-start justify-between gap-4">
        <PageHeader
          title={firstName ? `Bienvenido, ${firstName} 👋` : 'Bienvenido 👋'}
          subtitle={`Este es el resumen general de tu negocio — ${period.label.toLowerCase()}.`}
        />
        <Link
          to="/estandarizacion"
          className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-gold px-4 py-2.5 text-sm font-semibold text-navy-deep transition-colors hover:bg-gold/90"
        >
          <Upload className="h-4 w-4" /> Importar datos
        </Link>
      </div>

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
      ) : metrics && metrics.dimensiones?.monto === false ? (
        /* Fase 11: sin columna de monto el dashboard sería puro $0 — mejor
           decirlo claro y llevar al usuario al mapeo de columnas. */
        <EmptyState
          icon={Wallet}
          title="No detectamos la columna de ventas o monto"
          description="Tu archivo se procesó, pero ninguna columna se reconoció como monto de venta. Asígnala manualmente en el mapeo de columnas de Limpieza y el dashboard se calculará con tus datos."
          ctaLabel="Ir a asignar columnas"
          ctaTo="/limpieza"
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
                Tu archivo no trae una columna de <strong>costos</strong>: agrégala (o asígnala en
                el mapeo de Limpieza) para ver utilidad bruta, margen y resultado del periodo.
              </p>
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

          {/* Evolución + Indicadores clave */}
          <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
            <Card className="min-w-0">
              <h2 className="text-base font-semibold text-navy">
                Evolución de Ingresos, Gastos y Utilidad
              </h2>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={evolution} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
                    <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                    <XAxis
                      dataKey="mes"
                      tickFormatter={formatMonthShort}
                      tick={{ fill: AXIS_INK, fontSize: 12 }}
                      axisLine={{ stroke: GRID_STROKE }}
                      tickLine={false}
                    />
                    <YAxis
                      tickFormatter={formatCLPCompact}
                      tick={{ fill: AXIS_INK, fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                      width={60}
                    />
                    <Tooltip content={<ChartTooltip />} />
                    {evolution.length >= 2 && (
                      <ReferenceLine
                        y={evolution.reduce((s, m) => s + m.ingresos, 0) / evolution.length}
                        stroke={AXIS_INK}
                        strokeDasharray="6 4"
                        strokeOpacity={0.55}
                        label={{
                          value: 'promedio',
                          position: 'insideTopRight',
                          fill: AXIS_INK,
                          fontSize: 10,
                        }}
                      />
                    )}
                    <Line
                      type="monotone"
                      dataKey="ingresos"
                      name="Ingresos"
                      stroke={CHART.ingresos}
                      strokeWidth={2}
                      dot={{ r: 3, strokeWidth: 0, fill: CHART.ingresos }}
                      activeDot={{ r: 5 }}
                    />
                    {hasCosts && (
                      <Line
                        type="monotone"
                        dataKey="gastos"
                        name="Gastos"
                        stroke={CHART.gastos}
                        strokeWidth={2}
                        dot={{ r: 3, strokeWidth: 0, fill: CHART.gastos }}
                        activeDot={{ r: 5 }}
                      />
                    )}
                    {hasCosts && (
                      <Line
                        type="monotone"
                        dataKey="utilidad"
                        name="Utilidad"
                        stroke={CHART.utilidad}
                        strokeWidth={2}
                        dot={{ r: 3, strokeWidth: 0, fill: CHART.utilidad }}
                        activeDot={{ r: 5 }}
                      />
                    )}
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-2 flex flex-wrap gap-4 text-xs text-navy/70">
                {[
                  { name: 'Ingresos', color: CHART.ingresos, show: true },
                  { name: 'Gastos', color: CHART.gastos, show: hasCosts },
                  { name: 'Utilidad', color: CHART.utilidad, show: hasCosts },
                ]
                  .filter((s) => s.show)
                  .map((s) => (
                    <span key={s.name} className="flex items-center gap-1.5">
                      <span className="h-0.5 w-4 rounded" style={{ background: s.color }} />
                      {s.name}
                    </span>
                  ))}
              </div>
            </Card>

            <Card>
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
          </div>

          {/* Categorías + Estado financiero (solo si el archivo trae categorías) */}
          <div
            className={`mt-6 grid gap-6 ${
              (metrics.por_categoria ?? []).length > 0
                ? 'xl:grid-cols-[minmax(0,1fr)_340px]'
                : 'xl:grid-cols-2'
            }`}
          >
            {(metrics.por_categoria ?? []).length > 0 && (
            <Card className="min-w-0">
              <h2 className="text-base font-semibold text-navy">Análisis por Categoría</h2>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-navy/10 text-left text-xs font-semibold uppercase tracking-wide text-navy/50">
                      <th className="pb-2 pr-4">Categoría</th>
                      <th className="pb-2 pr-4 text-right">Ingresos</th>
                      <th className="pb-2 pr-4 text-right">% Ingresos</th>
                      <th className="pb-2 pr-4 text-right">Utilidad</th>
                      <th className="pb-2">Margen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(metrics.por_categoria ?? []).map((row) => (
                      <tr key={row.nombre} className="border-b border-navy/5">
                        <td className="py-2.5 pr-4 font-medium text-navy">{row.nombre}</td>
                        <td className="py-2.5 pr-4 text-right text-navy/75">{formatCLP(row.ingresos)}</td>
                        <td className="py-2.5 pr-4 text-right text-navy/75">
                          {formatNumber(row.porcentaje)}%
                        </td>
                        <td className="py-2.5 pr-4 text-right text-navy/75">
                          {row.utilidad !== undefined ? formatCLP(row.utilidad) : '—'}
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
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            )}

            <Card>
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
                      <p className="text-[11px] text-navy/50">Según el margen del periodo</p>
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

          {/* Canal + Top productos + Proyección — solo las tarjetas con datos
              reales del archivo (Fase 8: nada de recuadros vacíos) */}
          <div className="mt-6 grid gap-6 lg:grid-cols-2 2xl:grid-cols-3">
            {canal.length > 0 && (
            <Card className="min-w-0">
              <h2 className="text-base font-semibold text-navy">Ventas por {canalLabel}</h2>
              <div className="mt-2 flex flex-col items-center gap-3">
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
                          {formatNumber(entry.porcentaje)}%
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </Card>
            )}

            {topProducts.length > 0 && (
            <Card className="min-w-0">
              <h2 className="text-base font-semibold text-navy">Top Productos / Servicios</h2>
              <ul className="mt-4 space-y-3">
                {topProducts.map((product) => (
                  <li key={product.nombre}>
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <span className="truncate text-navy/80">{product.nombre}</span>
                      <span className="shrink-0 font-semibold text-navy">
                        {formatCLP(product.ingresos)}
                        <span className="ml-2 text-xs font-normal text-navy/45">
                          {formatNumber(product.porcentaje)}%
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

            <Card className="min-w-0">
              <h2 className="text-base font-semibold text-navy">Proyección (Próximos 3 meses)</h2>
              {metrics.proyeccion ? (
                <>
                  <p className="mt-2 text-sm text-navy/60">
                    Se proyecta un crecimiento de ingresos del
                  </p>
                  <p className="text-3xl font-bold text-navy">
                    {metrics.proyeccion.crecimiento_pct >= 0 ? '+' : ''}
                    {formatNumber(metrics.proyeccion.crecimiento_pct)}%
                  </p>
                  <p className="text-xs text-navy/50">mensual promedio</p>
                  <div className="mt-3 h-24">
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
                  <p className="mt-2 text-[11px] text-navy/45">
                    Proyección simple por crecimiento promedio mensual de tus ingresos históricos.
                    Línea punteada = proyección.
                  </p>
                </>
              ) : (
                <p className="mt-4 text-sm text-navy/50">
                  Se necesitan al menos 2 meses de historia para proyectar tus ingresos.
                </p>
              )}
            </Card>
          </div>
        </div>
      ) : null}
    </>
  )
}
