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
  CalendarDays,
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
  Users,
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
import ActiveSheetSelector from '../components/ActiveSheetSelector'
import ProductCatalogSummary from '../components/ProductCatalogSummary'
import AdaptiveProfileSummary from '../components/AdaptiveProfileSummary'
import ProfitabilityInsights from '../components/ProfitabilityInsights'
import { ALL_PERIOD, monthPeriod, useDataset } from '../data/DatasetContext'
import { useDemo } from '../demo/DemoContext'
import { DemoEmptyActions } from '../demo/DemoBanner'
import { principalPorParticipacionBruta } from '../lib/metrics'
import { analysisScopesEqual, serializedAnalysisScope } from '../lib/multiSheet'
import { soloMesesCompletos } from '../lib/partial'
import { getCachedMetrics, metricsCacheKey, requestMetrics } from '../lib/analysisCache'
import { ApiError, apiPost, apiPostJson, buildDatasetForm } from '../lib/api'
import { saveAnalysis } from '../lib/datasets'
import { AXIS_INK, CHART, GRID_STROKE, formatCLPCompact, formatMonthShort, truncateLabel } from '../lib/charts'
import { formatCLP, formatNumber, setActiveCurrency } from '../lib/format'
import type { DatasetDimensions, GroupRow, MetricsResult } from '../lib/types'

// ── Configuración del análisis ────────────────────────────────────────────────

type GroupBy = 'mes' | 'categoria' | 'producto' | 'canal'
type Metric = 'ingresos' | 'costo' | 'utilidad'

const GROUP_LABEL: Record<GroupBy, string> = {
  mes: 'Mes (tendencia)',
  categoria: 'Categoría',
  producto: 'Producto / Servicio',
  canal: 'Canal / Sucursal',
}

const METRIC_LABEL: Record<Metric, string> = {
  ingresos: 'Ingresos',
  costo: 'Costo',
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
  /** Tipo de análisis al que pertenece (Bug #10): permite priorizar los
   * hallazgos relevantes al preset activo en vez de mostrar siempre el mismo
   * set fijo sin importar si el usuario eligió Productos/Categorías/Canales. */
  category: GroupBy | 'general'
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

function trendVariationTone(value: number | null): string {
  if (value == null) return 'text-navy/40'
  if (value > 0) return 'text-green'
  if (value < 0) return 'text-coral'
  return 'text-navy/60'
}

function formatVariation(value: number): string {
  return `${value > 0 ? '+' : ''}${formatPct(value)}`
}

function computeFindings(m: MetricsResult): Finding[] {
  const findings: Finding[] = []
  // Fase 14b: los hallazgos usan SOLO meses completos — Explorar era el
  // único módulo que seguía comparando el mes parcial contra uno completo
  // (informaba una "caída" falsa y lo coronaba peor mes).
  const evo = soloMesesCompletos(m.evolucion_mensual)
  const huboParcial = evo.length < m.evolucion_mensual.length

  // Variación del último mes COMPLETO con datos
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
        detail: `Pasaron de ${formatCLP(prev.ingresos)} en ${formatMonthShort(prev.mes)} a ${formatCLP(last.ingresos)}.${
          huboParcial ? ' El mes con cobertura parcial no se compara como mes completo.' : ''
        }`,
        category: 'mes',
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
        category: 'mes',
      })
    }
  }

  // Concentración del producto top — SIEMPRE sobre la participación BRUTA
  // (una distribución que suma 100%); el % neto muestra devoluciones, pero
  // no sirve para afirmar dependencia. Fase 15: el backend calcula el líder
  // sobre TODOS los productos ANTES del recorte a 12 (lideres_productos) —
  // un producto con brutas altas y devoluciones altas ya no desaparece.
  const liderBruto = m.lideres_productos?.por_ventas_brutas
  const topProducto = liderBruto?.participacion_bruta_pct != null
    ? { nombre: liderBruto.nombre, participacion_bruta_pct: liderBruto.participacion_bruta_pct, porcentaje: liderBruto.participacion_bruta_pct }
    : principalPorParticipacionBruta(m.top_productos ?? [])
  const topProductoPct = topProducto?.participacion_bruta_pct ?? topProducto?.porcentaje
  if (topProducto && topProductoPct != null) {
    const alta = topProductoPct > 40
    findings.push({
      tone: alta ? 'gold' : 'teal',
      icon: Package,
      title: `"${topProducto.nombre}" concentra el ${formatPct(topProductoPct)} de tus ventas brutas`,
      detail: alta
        ? 'Alta dependencia de un solo producto: si sus ventas caen, tu negocio lo siente. Conviene diversificar.'
        : 'Concentración sana. Es tu producto más fuerte: hay espacio para potenciarlo aún más.',
      category: 'producto',
    })
  }

  // Mejor y peor margen por categoría (solo si el archivo trae costos)
  // Fase 12b §22: la comparación de rentabilidad exige una base mínima —
  // una categoría con UNA fila con costo no puede "ganar" contra una de mil.
  const conMargen = (m.por_categoria ?? []).filter(
    (c) =>
      c.margen_pct != null &&
      (c.cobertura_costos_pct == null || c.cobertura_costos_pct >= 30) &&
      (c.filas_pareadas == null || c.filas_pareadas >= 3),
  )
  if (conMargen.length >= 2) {
    const mejor = conMargen.reduce((a, b) => ((b.margen_pct ?? 0) > (a.margen_pct ?? 0) ? b : a))
    const peor = conMargen.reduce((a, b) => ((b.margen_pct ?? 0) < (a.margen_pct ?? 0) ? b : a))
    findings.push({
      tone: 'green',
      icon: Layers,
      title: `"${mejor.nombre}" es tu categoría más rentable (${formatPct(mejor.margen_pct ?? 0)} de margen)`,
      detail: `La menos rentable es "${peor.nombre}" con ${formatPct(peor.margen_pct ?? 0)}. Revisa precios o costos de esa línea.`,
      category: 'categoria',
    })
  }

  // Canal dominante (participación bruta: distribución real)
  const canales = m.ventas_por_canal ?? []
  if (canales.length >= 2) {
    const dominante = principalPorParticipacionBruta(canales)
    const dominantePct = dominante?.participacion_bruta_pct ?? dominante?.porcentaje
    if (dominante && dominantePct != null && dominantePct > 50) {
      findings.push({
        tone: 'gold',
        icon: Store,
        title: `"${dominante.nombre}" genera el ${formatPct(dominantePct)} de tus ventas brutas`,
        detail: 'Más de la mitad de tu venta depende de un solo canal. Fortalecer los demás reduce riesgo.',
        category: 'canal',
      })
    }
  }

  // Fase 12: concentración de clientes — el riesgo silencioso clásico de PyME
  if (
    m.clientes?.concentracion_top_pct != null &&
    m.clientes.concentracion_top_pct > 40 &&
    m.clientes.unicos >= 2
  ) {
    const topCliente = principalPorParticipacionBruta(m.clientes.top)
    findings.push({
      tone: 'gold',
      icon: Users,
      title: `Un solo cliente concentra el ${formatPct(m.clientes.concentracion_top_pct)} de tus ventas identificadas`,
      detail: `"${topCliente?.nombre ?? 'Tu cliente principal'}" pesa demasiado en tus ingresos: si se va, el negocio lo siente. Diversificar tu cartera reduce ese riesgo.`,
      category: 'general',
    })
  }

  // Fase 12: día de la semana con más venta (dotación, horarios, promociones)
  const dias = m.por_dia_semana ?? []
  if (dias.length >= 3) {
    const mejorDia = dias.reduce((a, b) => (b.ingresos > a.ingresos ? b : a))
    const totalSemana = dias.reduce((sum, d) => sum + d.ingresos, 0)
    if (totalSemana > 0) {
      const pct = (mejorDia.ingresos / totalSemana) * 100
      findings.push({
        tone: 'teal',
        icon: CalendarDays,
        title: `El ${mejorDia.dia} es tu mejor día (${formatPct(pct)} de la venta)`,
        detail: `Concentra tu dotación, horarios y promociones donde está la venta: ese día generaste ${formatCLP(mejorDia.ingresos)} en el periodo.`,
        category: 'general',
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
      category: 'mes',
    })
  }

  // Advertencias del motor de datos
  for (const advertencia of m.advertencias.slice(0, 1)) {
    findings.push({
      tone: 'gold',
      icon: AlertTriangle,
      title: 'Nota del motor de datos',
      detail: advertencia,
      category: 'general',
    })
  }

  return findings
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

/** Tick del eje de categorías del gráfico de barras horizontal (Productos
 * estrella, etc.): Recharts recorta el <text> SVG que se pasa del ancho
 * asignado al eje desde el borde IZQUIERDO, comiéndose la primera letra de
 * nombres largos ("Aceite maravilla 900ml" → ".ceite maravilla 900ml").
 * Truncamos el contenido con "…" antes de renderizar, y dejamos el nombre
 * completo en un <title> nativo (tooltip al pasar el mouse). */
function YAxisCategoryTick({
  x,
  y,
  payload,
}: {
  x?: number
  y?: number
  payload?: { value: string }
}) {
  if (x == null || y == null || !payload) return null
  return (
    <text x={x} y={y} dy={4} textAnchor="end" fontSize={12} fill={AXIS_INK}>
      {truncateLabel(payload.value)}
      <title>{payload.value}</title>
    </text>
  )
}

// ── Componente principal ──────────────────────────────────────────────────────

export default function Explorar() {
  // El "Rango" de Explorar comparte estado con el selector de periodo global
  // del topbar (Bug #8): antes eran dos filtros independientes y cambiar uno
  // no se reflejaba en el otro ni en el gráfico/hallazgos de esta página.
  const { file, cleaning, datasetId, storagePath, uploadedAt, metrics: contextMetrics, monthsAvailable, setMonthsAvailable, mappingOverride, sheet, sheetManifest, analysisScope, eliminarDuplicados, period: rango, setPeriod: setRango } = useDataset()
  // Fase 14: la demo ficticia sirve métricas congeladas del bundle (sin backend)
  const demo = useDemo()
  const ready = Boolean(file && cleaning) || demo.active

  const [groupBy, setGroupBy] = useState<GroupBy>('mes')
  const [metric, setMetric] = useState<Metric>('ingresos')

  const [fetchedMetrics, setMetrics] = useState<MetricsResult | null>(null)
  const metrics = demo.active ? demo.metrics : fetchedMetrics
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Fase 11 §9.3: "Reintentar" tras un timeout o corte de red
  const [retryTick, setRetryTick] = useState(0)
  const lastFetchKey = useRef<string | null>(null)
  const latestRequest = useRef(0)

  const [reco, setReco] = useState<{ recomendacion: string; plan: string[] } | null>(null)
  const [recoLoading, setRecoLoading] = useState(false)
  const [recoError, setRecoError] = useState<string | null>(null)

  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'ok' | 'fail'>('idle')

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
      analysisScopesEqual(contextMetrics.analysis_scope, analysisScope) &&
      !rango.from &&
      !rango.to &&
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
    if (rango.from) fields.date_from = rango.from
    if (rango.to) fields.date_to = rango.to
    requestMetrics(
      key,
      () => apiPost<MetricsResult>('/metrics', buildDatasetForm(file, storagePath, fields)),
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
        if (latestRequest.current === requestId && !controller.signal.aborted) setLoading(false)
      })
    return () => {
      controller.abort()
      // Fase 12b: liberar la clave al abortar (StrictMode/remontaje) — si
      // queda "ya pedida" con la petición abortada, la página no carga jamás.
      if (lastFetchKey.current === key) lastFetchKey.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demo.active, file, datasetId, storagePath, cleaning, contextMetrics, uploadedAt, rango, sheet, sheetManifest, analysisScope, mappingOverride, eliminarDuplicados, retryTick])

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
    if (metric !== 'ingresos' && !d.costo) setMetric('ingresos')
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
        >
          {/* Fase 14: conocer la plataforma sin datos propios */}
          <DemoEmptyActions />
        </EmptyState>
      </>
    )
  }

  if (metrics?.moneda_mixta) {
    return (
      <>
        <PageHeader
          title="Explorar datos"
          subtitle="La integridad monetaria debe resolverse antes de comparar resultados."
        />
        <EmptyState
          icon={AlertTriangle}
          title="Exploración monetaria bloqueada"
          description="El archivo mezcla monedas incompatibles en ventas o costos. El backend retiró sumas, rankings y proyecciones para impedir conclusiones inválidas. Corrige o separa las monedas y vuelve a limpiar el archivo."
          ctaLabel="Revisar en Limpieza"
          ctaTo="/limpieza"
        />
      </>
    )
  }

  if (metrics?.analisis_productos) {
    return (
      <>
        <PageHeader
          title="Explorar productos"
          subtitle="Costos, precios de lista, margen potencial y composicion del catalogo."
        />
        <ActiveSheetSelector />
        <ProductCatalogSummary analysis={metrics.analisis_productos} variant="explore" />
      </>
    )
  }

  if (metrics && (metrics.analisis_campanas || metrics.analisis_inventario || metrics.analisis_generico)) {
    return (
      <>
        <PageHeader
          title="Explorar datos"
          subtitle="Perfil adaptado al contenido real de esta hoja, sin inventar ventas."
        />
        <ActiveSheetSelector />
        <AdaptiveProfileSummary metrics={metrics} variant="explore" />
      </>
    )
  }

  const hasCosts = Boolean(metrics?.kpis.ganancia_neta)

  // Bug: `evolucion_mensual` del backend es SIEMPRE el histórico completo
  // (metrics.py: "Evolución mensual — siempre sobre el periodo completo"),
  // a propósito para el gráfico de contexto del Resumen. Explorar promete
  // que "Rango" filtra TODO el análisis, así que aquí se recorta en el
  // cliente a los meses dentro del rango elegido — sin tocar el campo
  // compartido que usan Resumen/Alertas/proyección.
  const evolucionEnRango = (metrics?.evolucion_mensual ?? []).filter((m) => {
    if (rango.from && m.mes < rango.from.slice(0, 7)) return false
    if (rango.to && m.mes > rango.to.slice(0, 7)) return false
    return true
  })
  const metricsEnRango = metrics ? { ...metrics, evolucion_mensual: evolucionEnRango } : null

  // Bug #10: el panel mostraba siempre el mismo set fijo sin importar el
  // preset activo. Los hallazgos del tipo de análisis elegido (mes/producto/
  // categoría/canal) suben primero; el resto completa el panel (sort estable:
  // conserva el orden relativo dentro de cada grupo).
  const findings = (metricsEnRango ? computeFindings(metricsEnRango) : [])
    .slice()
    .sort((a, b) => Number(a.category !== groupBy) - Number(b.category !== groupBy))
    .slice(0, 6)

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

  // Fase 12b §23: "sin datos de costo" NO es utilidad cero — un grupo sin
  // cobertura se excluye del gráfico de utilidad en vez de dibujar una barra $0.
  const valueOf = (row: GroupRow) =>
    metric === 'utilidad' ? row.utilidad ?? 0 : metric === 'costo' ? row.costo ?? 0 : row.ingresos
  const rowHasMetric = (row: GroupRow) =>
    metric === 'utilidad' ? row.utilidad != null : metric === 'costo' ? row.costo != null : true
  const barColor = metric === 'utilidad' ? CHART.utilidad : metric === 'costo' ? CHART.gastos : CHART.ingresos
  const chartRows = [...groupRows]
    .filter(rowHasMetric)
    .sort((a, b) => valueOf(b) - valueOf(a))
    .slice(0, 8)
  const excludedNoCost = metric !== 'ingresos' ? groupRows.length - groupRows.filter(rowHasMetric).length : 0

  // Fase 14b: utilidad DESCONOCIDA se mantiene null hasta el final — el
  // backend se corrigió específicamente para no inventar $0 y aquí un
  // `?? 0` la volvía a convertir en cero (gráfico, variaciones y
  // participaciones falsas incluidas).
  // Fase 19: el detalle mensual lleva SIEMPRE las cuatro columnas del negocio
  // cuando hay costos (ingresos, costo, utilidad y margen) — mirar solo la
  // métrica elegida escondía la historia completa de ventas + costos.
  const trendRows: Array<{
    mes: string
    valor: number | null
    ingresos: number | null
    costo: number | null
    utilidad: number | null
    margen: number | null
  }> = evolucionEnRango.map((m) => ({
    mes: formatMonthShort(m.mes),
    valor:
      metric === 'utilidad'
        ? m.utilidad ?? null
        : metric === 'costo'
          ? m.gastos ?? null
          : m.ingresos,
    ingresos: m.ingresos ?? null,
    costo: m.gastos ?? null,
    utilidad: m.utilidad ?? null,
    margen: m.margen_pareado_pct ?? null,
  }))
  const trendConDato = trendRows.filter((row) => row.valor != null)
  const trendTotal = trendConDato.reduce((sum, row) => sum + (row.valor ?? 0), 0)
  const monthlyDetailRows = trendRows
    .map((row, index) => {
      const previous = trendRows[index - 1]?.valor
      return {
        ...row,
        variacion:
          row.valor == null || previous == null || previous === 0
            ? null
            : ((row.valor - previous) / Math.abs(previous)) * 100,
        participacion:
          row.valor == null || trendTotal === 0 ? null : (row.valor / trendTotal) * 100,
      }
    })
    .slice(-8)
  const mesesSinCosto =
    metric !== 'ingresos' ? trendRows.length - trendConDato.length : 0

  const analysisLabel = `${METRIC_LABEL[metric]} por ${GROUP_LABEL[groupBy]} · ${rango.label}`

  const applyPreset = (preset: PresetAnalysis) => {
    setGroupBy(preset.groupBy)
    setMetric(preset.metric === 'utilidad' && !hasCosts ? 'ingresos' : preset.metric)
  }

  const generarRecomendacion = async () => {
    if (!metricsEnRango) return
    setRecoLoading(true)
    setRecoError(null)
    try {
      const result = await apiPostJson<{ recomendacion: string; plan: string[] }>(
        '/ai/recommendation',
        { metrics: metricsEnRango, hallazgos: findings.map((f) => f.title), analisis: analysisLabel },
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
    // Fase 14b (P0): la demo JAMÁS escribe en Supabase — sin este guard, un
    // clic guardaba hallazgos de la empresa ficticia en analyses/activity_log
    // e incluso podía asociarlos a un dataset REAL del usuario.
    if (demo.active || !metrics || metrics.moneda_mixta) return
    setSaveState('saving')
    const ok = await saveAnalysis(
      datasetId,
      analysisLabel,
      {
        rango: rango.label,
        agrupar_por: groupBy,
        metrica: metric,
        moneda: metrics.moneda,
        moneda_mixta: false,
        integridad_monetaria: 'verificada',
      },
      findings.map((f) => f.title),
      reco,
    )
    setSaveState(ok ? 'ok' : 'fail')
  }

  const selectClass =
    'w-full rounded-lg border border-navy/20 bg-white px-3 py-2 text-sm font-medium text-navy outline-none transition-colors focus:border-teal sm:w-auto'

  return (
    <>
      <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <PageHeader
          className="!mb-0"
          title="Explorar datos 🔍"
          subtitle="Encuentra respuestas, descubre patrones y entiende qué está pasando en tu negocio."
        />
        {/* Fase 14b: en la demo el botón NO existe — nada ficticio se guarda */}
        {!demo.active && (
          <button
            onClick={() => void guardarAnalisis()}
            disabled={saveState === 'saving' || !metrics}
            className="inline-flex w-full shrink-0 items-center justify-center gap-2 rounded-lg border border-navy/20 bg-white px-4 py-2.5 text-sm font-medium text-navy transition-colors hover:bg-navy/5 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
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
        )}
      </div>

      <ActiveSheetSelector />

      {hasCosts && metrics && <CostReliabilityAnalysis metrics={metrics} />}
      {/* Fase 19: Resumen muestra los números; Explorar los interpreta —
          portafolio por participación × margen, margen negativo, ventas bajo
          costo y evolución del margen, cada uno con su decisión. */}
      {hasCosts && metrics && <ProfitabilityInsights metrics={metrics} />}

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
          <div className="flex w-full items-center gap-2 pb-2 pr-2 sm:w-auto">
            <SlidersHorizontal className="h-4.5 w-4.5 text-teal" />
            <h2 className="text-base font-semibold text-navy">Define tu análisis</h2>
          </div>
          <label className="flex w-full flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-navy/50 sm:w-auto">
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
          <label className="flex w-full flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-navy/50 sm:w-auto">
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
          <label className="flex w-full flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-navy/50 sm:w-auto">
            Métrica
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value as Metric)}
              className={selectClass}
            >
              <option value="ingresos">Ingresos</option>
              <option value="costo" disabled={!hasCosts}>
                Costo{hasCosts ? '' : ' (requiere columna de costo)'}
              </option>
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
        <div className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
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
                          /* Fase 14b: utilidad desconocida = hueco en la línea,
                             jamás un punto en $0 */
                          connectNulls={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                    {mesesSinCosto > 0 && (
                      <p className="mt-2 text-xs text-navy/45">
                        {mesesSinCosto} mes(es) sin cobertura de costos: el valor se
                        muestra como hueco (no es $0, es desconocido).
                      </p>
                    )}
                  </div>
                )
              ) : chartRows.length === 0 ? (
                <p className="mt-6 text-sm text-navy/50">
                  {metric !== 'ingresos' && excludedNoCost > 0
                    ? `Ningún grupo tiene cobertura de costos: no hay ${METRIC_LABEL[metric].toLowerCase()} que graficar (elige "Ingresos").`
                    : `Tu archivo no tiene una columna de ${GROUP_LABEL[groupBy].toLowerCase()} que se pueda agrupar.`}
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
                        width={140}
                        tick={<YAxisCategoryTick />}
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

            {groupBy === 'mes' && monthlyDetailRows.length > 0 && (
              <Card className="min-w-0">
                <h2 className="text-base font-semibold text-navy">Detalle mensual</h2>
                <p className="mt-0.5 text-sm text-navy/60">
                  Comparación contra el mes anterior y peso dentro del período seleccionado.
                </p>

                <ul className="mt-4 divide-y divide-navy/5 sm:hidden">
                  {monthlyDetailRows.map((row) => (
                    <li
                      key={row.mes}
                      className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 py-3 text-sm"
                    >
                      <span className="font-semibold text-navy">{row.mes}</span>
                      <span className="text-right font-semibold text-navy">
                        {row.valor == null ? '—' : formatCLP(row.valor)}
                      </span>
                      <span className={`text-xs font-medium ${trendVariationTone(row.variacion)}`}>
                        {row.valor == null
                          ? 'Sin cobertura de costos'
                          : row.variacion == null
                            ? 'Mes base'
                            : `${formatVariation(row.variacion)} vs. anterior`}
                      </span>
                      <span className="text-right text-xs text-navy/50">
                        {row.participacion == null
                          ? 'Sin participación'
                          : `${formatPct(row.participacion)} del período`}
                      </span>
                    </li>
                  ))}
                </ul>

                <div className="mt-4 hidden overflow-x-auto sm:block">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-navy/10 text-left text-xs font-semibold uppercase tracking-wide text-navy/50">
                        <th className="pb-2 pr-4">Mes</th>
                        <th className="pb-2 pr-4 text-right">{METRIC_LABEL[metric]}</th>
                        <th className="pb-2 pr-4 text-right">Variación</th>
                        <th className="pb-2 pr-4 text-right">% del período</th>
                        {hasCosts && metric !== 'costo' && <th className="pb-2 pr-4 text-right">Costo</th>}
                        {hasCosts && metric !== 'utilidad' && <th className="pb-2 pr-4 text-right">Utilidad</th>}
                        {hasCosts && <th className="pb-2 text-right">Margen</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {monthlyDetailRows.map((row) => (
                        <tr key={row.mes} className="border-b border-navy/5">
                          <td className="py-2.5 pr-4 font-medium text-navy">{row.mes}</td>
                          <td className="py-2.5 pr-4 text-right text-navy/80">
                            {row.valor == null ? '—' : formatCLP(row.valor)}
                          </td>
                          <td
                            className={`py-2.5 pr-4 text-right font-medium ${trendVariationTone(row.variacion)}`}
                          >
                            {row.valor == null
                              ? '—'
                              : row.variacion == null
                                ? 'Base'
                                : formatVariation(row.variacion)}
                          </td>
                          <td className="py-2.5 pr-4 text-right text-navy/60">
                            {row.participacion == null ? '—' : formatPct(row.participacion)}
                          </td>
                          {hasCosts && metric !== 'costo' && (
                            <td className="py-2.5 pr-4 text-right text-navy/80">
                              {row.costo == null ? '—' : formatCLP(row.costo)}
                            </td>
                          )}
                          {hasCosts && metric !== 'utilidad' && (
                            <td className="py-2.5 pr-4 text-right text-navy/80">
                              {row.utilidad == null ? '—' : formatCLP(row.utilidad)}
                            </td>
                          )}
                          {hasCosts && (
                            <td className={`py-2.5 text-right font-medium ${
                              row.margen == null ? 'text-navy/40' : row.margen < 0 ? 'text-coral' : 'text-navy/80'
                            }`}>
                              {row.margen == null ? '—' : `${formatNumber(row.margen)}%`}
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {hasCosts && (
                  <p className="mt-3 text-xs text-navy/45">
                    Utilidad y margen usan solo filas con ingreso Y costo pareados; un mes sin
                    cobertura muestra “—” (desconocido, no $0).
                  </p>
                )}
                {trendRows.length > monthlyDetailRows.length && (
                  <p className="mt-3 text-xs text-navy/45">
                    Se muestran los 8 meses más recientes del período.
                  </p>
                )}
              </Card>
            )}

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
                        {hasCosts && <th className="pb-2 pr-4 text-right">Costo</th>}
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
                              {row.costo != null ? formatCLP(row.costo) : '—'}
                            </td>
                          )}
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
              ) : demo.active ? (
                /* Fase 14: la demo jamás llama a la IA (ni consume tokens) */
                <p className="mt-2 text-xs leading-relaxed text-navy/60">
                  En la demo, el asistente con IA está desactivado. Con un plan
                  activo, aquí recibes una recomendación interpretada de tus
                  propios datos, con plan de acción.
                </p>
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

function CostReliabilityAnalysis({ metrics }: { metrics: MetricsResult }) {
  const coverage = metrics.kpis.cobertura_costos
  const base = metrics.kpis.base_costos
  const margin = metrics.kpis.margen_utilidad_pct?.valor
  const quality = metrics.calidad_costos
  const excluded = metrics.exclusiones_indicadores?.filas_anuladas ?? 0
  const provenance = metrics.analysis_provenance as
    | { join?: { filas_sin_correspondencia?: unknown } }
    | undefined
  const unmatched = typeof provenance?.join?.filas_sin_correspondencia === 'number'
    ? provenance.join.filas_sin_correspondencia
    : null
  const origin = metrics.calculo_costos?.origen === 'cantidad_por_costo_unitario'
    ? `Cantidad × ${metrics.calculo_costos.columna_costo ?? 'costo unitario'}`
    : metrics.calculo_costos?.columna_costo ?? 'columna de costo'

  return (
    <Card className="mb-7 border-navy/15 bg-gradient-to-br from-navy/[0.035] via-white to-gold/[0.05]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-navy/45">
            Explorar · confiabilidad del margen
          </p>
          <h2 className="mt-1 text-base font-semibold text-navy">¿Qué tan explicable es la utilidad?</h2>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-navy/65">
            Esta vista no repite el Resumen: comprueba cobertura, correspondencias y valores
            atípicos antes de comparar costo, utilidad o margen por producto, categoría y canal.
          </p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
          (coverage?.pct ?? 0) >= 95 ? 'bg-green/10 text-green' : 'bg-gold/15 text-navy'
        }`}>
          {coverage ? `${formatNumber(coverage.pct)}% con costo` : 'Cobertura desconocida'}
        </span>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <CostContextItem
          label="Base pareada"
          value={coverage ? `${formatNumber(coverage.filas_con_ingreso_y_costo)} de ${formatNumber(coverage.filas_con_ingreso)}` : '—'}
          detail="ventas con ingreso y costo legibles"
        />
        <CostContextItem
          label="Cálculo usado"
          value={origin}
          detail="el costo unitario nunca se suma directamente"
        />
        <CostContextItem
          label="Margen pareado"
          value={margin == null ? '—' : `${formatNumber(margin)}%`}
          detail={base ? `${formatCLP(base.ingresos_pareados)} de ingresos comparables` : 'requiere ingreso y costo en la misma fila'}
        />
        <CostContextItem
          label="Correspondencias"
          value={unmatched == null ? '—' : `${formatNumber(unmatched)} sin SKU`}
          detail="filas conservadas sin costo de referencia"
        />
      </div>
      {(quality?.registros_atipicos || excluded > 0) && (
        <div className="mt-4 grid gap-2 lg:grid-cols-2">
          {(quality?.registros_atipicos ?? 0) > 0 && (
            <p className="rounded-lg border border-gold/35 bg-gold/[0.08] px-3 py-2 text-xs leading-relaxed text-navy/70">
              {formatNumber(quality?.registros_atipicos ?? 0)} costo(s) no positivos o atípicos
              concentran {formatNumber(quality?.participacion_costo_absoluto_pct ?? 0)}% del costo
              absoluto. Se conservan, pero pueden dominar el margen.
            </p>
          )}
          {excluded > 0 && (
            <p className="rounded-lg border border-teal/25 bg-teal/[0.06] px-3 py-2 text-xs leading-relaxed text-navy/70">
              {formatNumber(excluded)} venta(s) anulada(s) permanecen en la base y se excluyen de
              los indicadores, tal como exige el estado del documento.
            </p>
          )}
        </div>
      )}
    </Card>
  )
}

function CostContextItem({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  detail: string
}) {
  return (
    <div className="rounded-xl border border-navy/10 bg-white/85 p-3.5">
      <p className="text-[11px] text-navy/45">{label}</p>
      <p className="mt-1 text-sm font-bold text-navy">{value}</p>
      <p className="mt-1 text-[11px] leading-relaxed text-navy/50">{detail}</p>
    </div>
  )
}
