/**
 * Explorar datos (SPEC §7 — Fase 4, MVP básico).
 *
 * "¿Qué quieres descubrir hoy?" (análisis predefinidos) → "Define tu análisis"
 * (rango, agrupar por, métrica) → "Hallazgos principales" con gráfico →
 * "Profundiza" (tabla) → "Recomendación inteligente" (IA a pedido, nunca
 * automática) → Guardar análisis (best-effort en Supabase, migración 0004).
 *
 * Regla no negociable: sin dataset limpio no hay análisis.
 */

import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Layers,
  Lightbulb,
  Loader2,
  Package,
  Save,
  Search,
  SlidersHorizontal,
  Sparkles,
  Store,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import { ALL_PERIOD, monthPeriod, useDataset, type Period } from '../data/DatasetContext'
import { ApiError, apiPost, apiPostJson, buildDatasetForm } from '../lib/api'
import { saveAnalysis } from '../lib/datasets'
import { AXIS_INK, CHART, GRID_STROKE, formatCLPCompact, formatMonthShort } from '../lib/charts'
import { formatCLP, setActiveCurrency } from '../lib/format'
import type { DatasetDimensions, GroupRow, MetricsResult } from '../lib/types'

// ── Configuración del análisis ────────────────────────────────────────────────

type GroupBy = 'mes' | 'categoria' | 'producto' | 'canal'
type Metric = 'ingresos' | 'utilidad'

const GROUP_LABEL: Record<GroupBy, string> = {
  mes: 'Mes (tendencia)',
  categoria: 'Categoría',
  producto: 'Producto / Servicio',
  canal: 'Canal / Sucursal',
}

const METRIC_LABEL: Record<Metric, string> = {
  ingresos: 'Ingresos',
  utilidad: 'Utilidad',
}

interface PresetAnalysis {
  icon: LucideIcon
  title: string
  question: string
  groupBy: GroupBy
  metric: Metric
  tone: string
}

const PRESETS: PresetAnalysis[] = [
  {
    icon: TrendingUp,
    title: 'Tendencia de ventas',
    question: '¿Cómo evolucionan mis ingresos mes a mes?',
    groupBy: 'mes',
    metric: 'ingresos',
    tone: 'bg-teal/10 text-teal',
  },
  {
    icon: Package,
    title: 'Productos estrella',
    question: '¿Qué productos concentran mis ingresos?',
    groupBy: 'producto',
    metric: 'ingresos',
    tone: 'bg-gold/15 text-gold',
  },
  {
    icon: Layers,
    title: 'Categorías rentables',
    question: '¿Qué categoría deja la mejor utilidad?',
    groupBy: 'categoria',
    metric: 'utilidad',
    tone: 'bg-green/10 text-green',
  },
  {
    icon: Store,
    title: 'Canales y sucursales',
    question: '¿Dónde estoy vendiendo más?',
    groupBy: 'canal',
    metric: 'ingresos',
    tone: 'bg-navy/10 text-navy',
  },
]

// ── Hallazgos: lectura automática de las métricas (sin IA, sin costo) ─────────

type FindingTone = 'green' | 'gold' | 'coral' | 'teal'

interface Finding {
  tone: FindingTone
  icon: LucideIcon
  title: string
  detail: string
}

const TONE_STYLE: Record<FindingTone, string> = {
  green: 'bg-green/10 text-green',
  gold: 'bg-gold/15 text-gold',
  coral: 'bg-coral/10 text-coral',
  teal: 'bg-teal/10 text-teal',
}

function formatPct(value: number): string {
  return `${value.toLocaleString('es-CL', { maximumFractionDigits: 1 })}%`
}

function computeFindings(m: MetricsResult): Finding[] {
  const findings: Finding[] = []
  const evo = m.evolucion_mensual

  // Variación del último mes con datos
  if (evo.length >= 2) {
    const last = evo[evo.length - 1]
    const prev = evo[evo.length - 2]
    if (prev.ingresos > 0) {
      const pct = ((last.ingresos - prev.ingresos) / prev.ingresos) * 100
      const up = pct >= 0
      findings.push({
        tone: up ? 'green' : 'coral',
        icon: up ? ArrowUpRight : ArrowDownRight,
        title: `Tus ingresos ${up ? 'subieron' : 'cayeron'} ${formatPct(Math.abs(pct))} en ${formatMonthShort(last.mes)}`,
        detail: `Pasaron de ${formatCLP(prev.ingresos)} en ${formatMonthShort(prev.mes)} a ${formatCLP(last.ingresos)}.`,
      })
    }
    const best = evo.reduce((a, b) => (b.ingresos > a.ingresos ? b : a))
    const worst = evo.reduce((a, b) => (b.ingresos < a.ingresos ? b : a))
    if (best.mes !== worst.mes) {
      findings.push({
        tone: 'teal',
        icon: TrendingUp,
        title: `Tu mejor mes fue ${formatMonthShort(best.mes)}`,
        detail: `Ingresos de ${formatCLP(best.ingresos)}. El más bajo fue ${formatMonthShort(worst.mes)} con ${formatCLP(worst.ingresos)}.`,
      })
    }
  }

  // Concentración del producto top
  const topProducto = m.top_productos?.[0]
  if (topProducto) {
    const alta = topProducto.porcentaje > 40
    findings.push({
      tone: alta ? 'gold' : 'teal',
      icon: Package,
      title: `"${topProducto.nombre}" concentra el ${formatPct(topProducto.porcentaje)} de tus ingresos`,
      detail: alta
        ? 'Alta dependencia de un solo producto: si sus ventas caen, tu negocio lo siente. Conviene diversificar.'
        : 'Concentración sana. Es tu producto más fuerte: hay espacio para potenciarlo aún más.',
    })
  }

  // Mejor y peor margen por categoría (solo si el archivo trae costos)
  const conMargen = (m.por_categoria ?? []).filter((c) => c.margen_pct != null)
  if (conMargen.length >= 2) {
    const mejor = conMargen.reduce((a, b) => ((b.margen_pct ?? 0) > (a.margen_pct ?? 0) ? b : a))
    const peor = conMargen.reduce((a, b) => ((b.margen_pct ?? 0) < (a.margen_pct ?? 0) ? b : a))
    findings.push({
      tone: 'green',
      icon: Layers,
      title: `"${mejor.nombre}" es tu categoría más rentable (${formatPct(mejor.margen_pct ?? 0)} de margen)`,
      detail: `La menos rentable es "${peor.nombre}" con ${formatPct(peor.margen_pct ?? 0)}. Revisa precios o costos de esa línea.`,
    })
  }

  // Canal dominante
  const canales = m.ventas_por_canal ?? []
  if (canales.length >= 2) {
    const dominante = canales[0]
    if (dominante.porcentaje > 50) {
      findings.push({
        tone: 'gold',
        icon: Store,
        title: `"${dominante.nombre}" genera el ${formatPct(dominante.porcentaje)} de tus ventas`,
        detail: 'Más de la mitad de tus ingresos depende de un solo canal. Fortalecer los demás reduce riesgo.',
      })
    }
  }

  // Proyección
  if (m.proyeccion) {
    const crec = m.proyeccion.crecimiento_pct
    findings.push({
      tone: crec >= 0 ? 'green' : 'coral',
      icon: crec >= 0 ? ArrowUpRight : ArrowDownRight,
      title: `Proyección: ${crec >= 0 ? 'crecimiento' : 'caída'} de ${formatPct(Math.abs(crec))} mensual`,
      detail: `Si la tendencia se mantiene, el próximo mes cerrarías en torno a ${formatCLP(m.proyeccion.meses[0]?.ingresos ?? 0)}.`,
    })
  }

  // Advertencias del motor de datos
  for (const advertencia of m.advertencias.slice(0, 1)) {
    findings.push({ tone: 'gold', icon: AlertTriangle, title: 'Nota del motor de datos', detail: advertencia })
  }

  return findings.slice(0, 6)
}

// ── Tooltip compartido (mismo estilo del Resumen) ────────────────────────────

function ChartTooltip({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-navy/10 bg-white px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-semibold text-navy">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} className="flex items-center gap-1.5 text-navy/70">
          <span className="h-2 w-2 rounded-full" style={{ background: entry.color }} />
          {entry.name}: <span className="font-semibold text-navy">{formatCLP(entry.value)}</span>
        </p>
      ))}
    </div>
  )
}

// ── Componente principal ──────────────────────────────────────────────────────

export default function Explorar() {
  const { file, cleaning, datasetId, storagePath, uploadedAt, monthsAvailable, setMonthsAvailable, mappingOverride, sheet } = useDataset()
  const ready = Boolean(file && cleaning)

  const [rango, setRango] = useState<Period>(ALL_PERIOD)
  const [groupBy, setGroupBy] = useState<GroupBy>('mes')
  const [metric, setMetric] = useState<Metric>('ingresos')

  const [metrics, setMetrics] = useState<MetricsResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Fase 11 §9.3: "Reintentar" tras un timeout o corte de red
  const [retryTick, setRetryTick] = useState(0)
  const lastFetchKey = useRef<string | null>(null)

  const [reco, setReco] = useState<{ recomendacion: string; plan: string[] } | null>(null)
  const [recoLoading, setRecoLoading] = useState(false)
  const [recoError, setRecoError] = useState<string | null>(null)

  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'ok' | 'fail'>('idle')

  // Métricas del rango seleccionado (uploadedAt distingue cargas con igual nombre)
  useEffect(() => {
    if (!file || !cleaning) return
    const datasetKey = datasetId ?? storagePath ?? String(uploadedAt?.getTime() ?? 0)
    // Mapeo manual y reintento en la clave: cambiar el mapeo refresca el análisis
    const key = `${datasetKey}|${rango.from}|${rango.to}|${sheet ?? ''}|${JSON.stringify(mappingOverride ?? {})}|${retryTick}`
    if (lastFetchKey.current === key) return
    lastFetchKey.current = key
    setLoading(true)
    setError(null)
    const fields: Record<string, string> = {}
    if (mappingOverride) fields.mapping = JSON.stringify(mappingOverride)
    if (sheet) fields.sheet = sheet
    if (rango.from) fields.date_from = rango.from
    if (rango.to) fields.date_to = rango.to
    apiPost<MetricsResult>('/metrics', buildDatasetForm(file, storagePath, fields))
      .then((result) => {
        setMetrics(result)
        setActiveCurrency(result.moneda)
        if (monthsAvailable.length === 0 && result.periodo.meses_disponibles.length > 0) {
          setMonthsAvailable(result.periodo.meses_disponibles)
        }
      })
      .catch((err) => {
        // Anular la clave: sin esto el próximo render "cree" que ya se pidió
        // y la página queda vacía hasta recargar (Fase 11 §9.3).
        lastFetchKey.current = null
        setError(err instanceof ApiError ? err.message : 'No se pudo calcular el análisis.')
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, datasetId, storagePath, cleaning, uploadedAt, rango, sheet, mappingOverride, retryTick])

  // Al cambiar el análisis, la recomendación anterior deja de aplicar
  useEffect(() => {
    setReco(null)
    setRecoError(null)
    setSaveState('idle')
  }, [rango, groupBy, metric, uploadedAt])

  // Fase 8: si la agrupación activa no existe en este archivo, volver a una
  // disponible (ej: archivo sin canal → jamás quedarse pegado en "canal").
  useEffect(() => {
    if (!metrics?.dimensiones) return
    const d = metrics.dimensiones
    const available: Record<GroupBy, boolean> = {
      mes: d.fecha,
      categoria: d.categoria,
      producto: d.producto,
      canal: d.canal || d.sucursal,
    }
    if (!available[groupBy]) {
      const fallback = (Object.keys(available) as GroupBy[]).find((k) => available[k])
      setGroupBy(fallback ?? 'mes')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metrics])

  if (!ready) {
    return (
      <>
        <PageHeader
          title="Explorar datos"
          subtitle="Encuentra respuestas, descubre patrones y entiende qué está pasando en tu negocio."
        />
        <EmptyState
          icon={Search}
          title="No hay datos que explorar todavía"
          description="Cuando tengas un dataset limpio podrás hacer análisis guiados, ver hallazgos principales y recibir recomendaciones inteligentes."
          ctaLabel="Cargar mis datos"
          ctaTo="/estandarizacion"
        />
      </>
    )
  }

  const hasCosts = Boolean(metrics?.kpis.ganancia_neta)
  const findings = metrics ? computeFindings(metrics) : []

  // ── Fase 8: los análisis se adaptan a las columnas REALES del archivo ──
  // Sin columna de canal/sucursal no se ofrece ese análisis (no botones
  // inútiles); lo mismo para categoría, producto o fechas.
  const dims: DatasetDimensions | undefined = metrics?.dimensiones
  const groupAvailable: Record<GroupBy, boolean> = {
    mes: !dims || dims.fecha,
    categoria: !dims || dims.categoria,
    producto: !dims || dims.producto,
    canal: !dims || dims.canal || dims.sucursal,
  }
  const visiblePresets = PRESETS.filter((preset) => groupAvailable[preset.groupBy])
  const hiddenCount = PRESETS.length - visiblePresets.length

  // Filas del gráfico y la tabla según la agrupación activa
  const groupRows: GroupRow[] =
    groupBy === 'categoria'
      ? metrics?.por_categoria ?? []
      : groupBy === 'canal'
        ? metrics?.ventas_por_canal ?? []
        : groupBy === 'producto'
          ? metrics?.top_productos ?? []
          : []

  const valueOf = (row: GroupRow) => (metric === 'utilidad' ? row.utilidad ?? 0 : row.ingresos)
  const barColor = metric === 'utilidad' ? CHART.utilidad : CHART.ingresos
  const chartRows = [...groupRows].sort((a, b) => valueOf(b) - valueOf(a)).slice(0, 8)

  const trendRows = (metrics?.evolucion_mensual ?? []).map((m) => ({
    mes: formatMonthShort(m.mes),
    valor: metric === 'utilidad' ? m.utilidad ?? 0 : m.ingresos,
  }))

  const analysisLabel = `${METRIC_LABEL[metric]} por ${GROUP_LABEL[groupBy]} · ${rango.label}`

  const applyPreset = (preset: PresetAnalysis) => {
    setGroupBy(preset.groupBy)
    setMetric(preset.metric === 'utilidad' && !hasCosts ? 'ingresos' : preset.metric)
  }

  const generarRecomendacion = async () => {
    if (!metrics) return
    setRecoLoading(true)
    setRecoError(null)
    try {
      const result = await apiPostJson<{ recomendacion: string; plan: string[] }>(
        '/ai/recommendation',
        { metrics, hallazgos: findings.map((f) => f.title), analisis: analysisLabel },
      )
      setReco(result)
    } catch (err) {
      setRecoError(
        err instanceof ApiError ? err.message : 'No se pudo generar la recomendación.',
      )
    } finally {
      setRecoLoading(false)
    }
  }

  const guardarAnalisis = async () => {
    setSaveState('saving')
    const ok = await saveAnalysis(
      datasetId,
      analysisLabel,
      { rango: rango.label, agrupar_por: groupBy, metrica: metric },
      findings.map((f) => f.title),
      reco,
    )
    setSaveState(ok ? 'ok' : 'fail')
  }

  const selectClass =
    'rounded-lg border border-navy/20 bg-white px-3 py-2 text-sm font-medium text-navy outline-none transition-colors focus:border-teal'

  return (
    <>
      <div className="flex items-start justify-between gap-4">
        <PageHeader
          title="Explorar datos 🔍"
          subtitle="Encuentra respuestas, descubre patrones y entiende qué está pasando en tu negocio."
        />
        <button
          onClick={() => void guardarAnalisis()}
          disabled={saveState === 'saving' || !metrics}
          className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-navy/20 bg-white px-4 py-2.5 text-sm font-medium text-navy transition-colors hover:bg-navy/5 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {saveState === 'saving' ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          {saveState === 'ok'
            ? 'Análisis guardado ✓'
            : saveState === 'fail'
              ? 'No se pudo guardar'
              : 'Guardar análisis'}
        </button>
      </div>

      {/* ¿Qué quieres descubrir hoy? (adaptado a las columnas del archivo) */}
      <div>
        <h2 className="text-lg font-semibold text-navy">¿Qué quieres descubrir hoy?</h2>
        <p className="mt-0.5 text-sm text-navy/60">
          Parte de una pregunta típica o define tu propio análisis abajo.
          {hiddenCount > 0 && (
            <span className="text-navy/45">
              {' '}
              Los análisis se adaptan a las columnas de tu archivo.
            </span>
          )}
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {visiblePresets.map((preset) => {
            const active =
              groupBy === preset.groupBy &&
              (metric === preset.metric || (preset.metric === 'utilidad' && !hasCosts))
            return (
              <button
                key={preset.title}
                onClick={() => applyPreset(preset)}
                className={`rounded-2xl border p-5 text-left transition-colors ${
                  active
                    ? 'border-teal bg-teal/5'
                    : 'border-navy/10 bg-white hover:border-teal/50'
                }`}
              >
                <div className={`flex h-10 w-10 items-center justify-center rounded-full ${preset.tone}`}>
                  <preset.icon className="h-5 w-5" />
                </div>
                <h3 className="mt-3 text-sm font-semibold text-navy">{preset.title}</h3>
                <p className="mt-1 text-xs leading-relaxed text-navy/60">{preset.question}</p>
              </button>
            )
          })}
        </div>
      </div>

      {/* Define tu análisis */}
      <Card className="mt-8">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex items-center gap-2 pb-2 pr-2">
            <SlidersHorizontal className="h-4.5 w-4.5 text-teal" />
            <h2 className="text-base font-semibold text-navy">Define tu análisis</h2>
          </div>
          <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-navy/50">
            Rango
            <select
              value={rango.label}
              onChange={(e) => {
                const month = monthsAvailable.find((m) => monthPeriod(m).label === e.target.value)
                setRango(month ? monthPeriod(month) : ALL_PERIOD)
              }}
              className={selectClass}
            >
              <option value={ALL_PERIOD.label}>{ALL_PERIOD.label}</option>
              {monthsAvailable.map((m) => (
                <option key={m} value={monthPeriod(m).label}>
                  {formatMonthShort(m)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-navy/50">
            Agrupar por
            <select
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value as GroupBy)}
              className={selectClass}
            >
              {(Object.keys(GROUP_LABEL) as GroupBy[])
                .filter((key) => groupAvailable[key])
                .map((key) => (
                  <option key={key} value={key}>
                    {GROUP_LABEL[key]}
                  </option>
                ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-navy/50">
            Métrica
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value as Metric)}
              className={selectClass}
            >
              <option value="ingresos">Ingresos</option>
              <option value="utilidad" disabled={!hasCosts}>
                Utilidad{hasCosts ? '' : ' (requiere columna de costo)'}
              </option>
            </select>
          </label>
        </div>
      </Card>

      {/* Resultados: gráfico + hallazgos / profundiza + recomendación */}
      {error ? (
        <Card className="mt-6 border-coral/40 bg-coral/5">
          <div className="flex flex-wrap items-start gap-2 text-sm text-coral">
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
        </Card>
      ) : (
        <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="flex min-w-0 flex-col gap-6">
            {/* Gráfico principal */}
            <Card>
              <h2 className="text-base font-semibold text-navy">
                {METRIC_LABEL[metric]}{' '}
                {groupBy === 'mes' ? 'mes a mes' : `por ${GROUP_LABEL[groupBy].toLowerCase()}`}
              </h2>
              <p className="mt-0.5 text-sm text-navy/60">{rango.label}</p>
              {loading ? (
                <div className="flex h-64 items-center justify-center">
                  <Loader2 className="h-7 w-7 animate-spin text-teal" />
                </div>
              ) : groupBy === 'mes' ? (
                trendRows.length === 0 ? (
                  <p className="mt-6 text-sm text-navy/50">Sin datos en el rango seleccionado.</p>
                ) : (
                  <div className="mt-4 h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={trendRows} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
                        <XAxis
                          dataKey="mes"
                          tick={{ fill: AXIS_INK, fontSize: 12 }}
                          axisLine={false}
                          tickLine={false}
                        />
                        <YAxis
                          tickFormatter={formatCLPCompact}
                          tick={{ fill: AXIS_INK, fontSize: 11 }}
                          axisLine={false}
                          tickLine={false}
                          width={64}
                        />
                        <Tooltip content={<ChartTooltip />} />
                        <Line
                          type="monotone"
                          dataKey="valor"
                          name={METRIC_LABEL[metric]}
                          stroke={barColor}
                          strokeWidth={2}
                          dot={false}
                          activeDot={{ r: 5, strokeWidth: 2, stroke: '#ffffff' }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )
              ) : chartRows.length === 0 ? (
                <p className="mt-6 text-sm text-navy/50">
                  Tu archivo no tiene una columna de {GROUP_LABEL[groupBy].toLowerCase()} que se
                  pueda agrupar.
                </p>
              ) : (
                <div className="mt-4" style={{ height: chartRows.length * 44 + 48 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={chartRows}
                      layout="vertical"
                      margin={{ top: 4, right: 56, bottom: 0, left: 8 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
                      <XAxis
                        type="number"
                        tickFormatter={formatCLPCompact}
                        tick={{ fill: AXIS_INK, fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        type="category"
                        dataKey="nombre"
                        width={132}
                        tick={{ fill: AXIS_INK, fontSize: 12 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(26,58,82,0.04)' }} />
                      <Bar
                        dataKey={(row: GroupRow) => valueOf(row)}
                        name={METRIC_LABEL[metric]}
                        fill={barColor}
                        radius={[0, 4, 4, 0]}
                        barSize={18}
                      >
                        <LabelList
                          dataKey={(row: GroupRow) => valueOf(row)}
                          position="right"
                          formatter={(v) => formatCLPCompact(Number(v))}
                          style={{ fill: AXIS_INK, fontSize: 11 }}
                        />
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>

            {/* Profundiza */}
            {groupBy !== 'mes' && chartRows.length > 0 && (
              <Card className="min-w-0">
                <h2 className="text-base font-semibold text-navy">Profundiza</h2>
                <p className="mt-0.5 text-sm text-navy/60">
                  El detalle de {GROUP_LABEL[groupBy].toLowerCase()} en el rango seleccionado.
                </p>
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-navy/10 text-left text-xs font-semibold uppercase tracking-wide text-navy/50">
                        <th className="pb-2 pr-4">{GROUP_LABEL[groupBy]}</th>
                        <th className="pb-2 pr-4 text-right">Ingresos</th>
                        <th className="pb-2 pr-4 text-right">% del total</th>
                        {hasCosts && <th className="pb-2 pr-4 text-right">Utilidad</th>}
                        {hasCosts && <th className="pb-2 text-right">Margen</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {groupRows.map((row) => (
                        <tr key={row.nombre} className="border-b border-navy/5">
                          <td className="py-2.5 pr-4 font-medium text-navy">{row.nombre}</td>
                          <td className="py-2.5 pr-4 text-right text-navy/80">
                            {formatCLP(row.ingresos)}
                          </td>
                          <td className="py-2.5 pr-4 text-right text-navy/60">
                            {formatPct(row.porcentaje)}
                          </td>
                          {hasCosts && (
                            <td className="py-2.5 pr-4 text-right text-navy/80">
                              {row.utilidad != null ? formatCLP(row.utilidad) : '—'}
                            </td>
                          )}
                          {hasCosts && (
                            <td className="py-2.5 text-right text-navy/60">
                              {row.margen_pct != null ? formatPct(row.margen_pct) : '—'}
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

          {/* Columna derecha: hallazgos + recomendación */}
          <div className="flex flex-col gap-6">
            <Card>
              <div className="flex items-center gap-2">
                <Lightbulb className="h-4.5 w-4.5 text-gold" />
                <h2 className="text-base font-semibold text-navy">Hallazgos principales</h2>
              </div>
              {loading ? (
                <div className="flex h-32 items-center justify-center">
                  <Loader2 className="h-6 w-6 animate-spin text-teal" />
                </div>
              ) : findings.length === 0 ? (
                <p className="mt-3 text-sm text-navy/50">
                  Sin hallazgos destacables en el rango seleccionado.
                </p>
              ) : (
                <ul className="mt-4 space-y-4">
                  {findings.map((finding) => (
                    <li key={finding.title} className="flex items-start gap-3">
                      <div
                        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${TONE_STYLE[finding.tone]}`}
                      >
                        <finding.icon className="h-4 w-4" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold leading-snug text-navy">
                          {finding.title}
                        </p>
                        <p className="mt-0.5 text-xs leading-relaxed text-navy/60">
                          {finding.detail}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            {/* Recomendación inteligente — IA solo a pedido */}
            <Card className="border-gold/30 bg-gold/5">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4.5 w-4.5 text-gold" />
                <h2 className="text-base font-semibold text-navy">Recomendación inteligente</h2>
              </div>
              {reco ? (
                <>
                  <p className="mt-3 text-sm leading-relaxed text-navy/80">{reco.recomendacion}</p>
                  {reco.plan.length > 0 && (
                    <div className="mt-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-navy/50">
                        Plan de acción
                      </p>
                      <ul className="mt-2 space-y-2">
                        {reco.plan.map((paso, i) => (
                          <li key={paso} className="flex items-start gap-2.5 text-sm text-navy/80">
                            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-teal text-[10px] font-bold text-white">
                              {i + 1}
                            </span>
                            {paso}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <button
                    onClick={() => void generarRecomendacion()}
                    disabled={recoLoading}
                    className="mt-4 text-xs font-semibold text-teal hover:underline disabled:opacity-50"
                  >
                    {recoLoading ? 'Generando…' : 'Volver a generar'}
                  </button>
                </>
              ) : (
                <>
                  <p className="mt-2 text-xs leading-relaxed text-navy/60">
                    Tu analista con IA interpreta este análisis y te entrega una recomendación con
                    plan de acción. Se genera solo cuando tú lo pides.
                  </p>
                  {recoError && (
                    <div className="mt-3 flex items-start gap-2 rounded-lg border border-coral/40 bg-coral/10 px-3 py-2 text-xs text-coral">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      <p>{recoError}</p>
                    </div>
                  )}
                  <button
                    onClick={() => void generarRecomendacion()}
                    disabled={recoLoading || loading || !metrics}
                    className="mt-4 inline-flex items-center gap-2 rounded-lg bg-teal px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal/90 disabled:cursor-not-allowed disabled:bg-teal/50"
                  >
                    {recoLoading ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" /> Analizando tu negocio…
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4" /> Generar recomendación con IA
                      </>
                    )}
                  </button>
                </>
              )}
              <p className="mt-3 flex items-center gap-1.5 text-[10px] text-navy/40">
                <CheckCircle2 className="h-3 w-3" /> IA puede cometer errores. Verifica la
                información.
              </p>
            </Card>
          </div>
        </div>
      )}
    </>
  )
}
