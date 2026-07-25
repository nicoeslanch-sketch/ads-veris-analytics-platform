import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  Calculator,
  CheckCircle2,
  CircleDollarSign,
  CircleHelp,
  Link2,
  Package,
  Receipt,
  Scale,
  Target,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import Card from './ui/Card'
import Badge from './ui/Badge'
import {
  AXIS_INK,
  CATEGORICAL,
  CHART,
  GRID_STROKE,
  formatCLPCompact,
  formatMonthShort,
  truncateLabel,
} from '../lib/charts'
import { formatCLP, formatNumber } from '../lib/format'
import type { BusinessAnalysis, BusinessGroupRow } from '../lib/types'

type Variant = 'summary' | 'explore'

function money(value: number | null | undefined) {
  return value == null ? 'No disponible' : formatCLP(value)
}

function percent(value: number | null | undefined) {
  return value == null ? 'No disponible' : `${formatNumber(value)}%`
}

function numeric(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function certificationMeta(state: BusinessAnalysis['estado_certificacion']) {
  if (state === 'certified') {
    return {
      label: 'Resultado verificable',
      note: 'Las relaciones y coberturas permiten usar los indicadores como resultado final.',
      tone: 'green' as const,
      classes: 'border-green/30 bg-green/[0.07]',
    }
  }
  if (state === 'partial') {
    return {
      label: 'Resultado parcial',
      note: 'Los indicadores disponibles son útiles, pero todavía tienen cobertura incompleta.',
      tone: 'gold' as const,
      classes: 'border-gold/35 bg-gold/[0.08]',
    }
  }
  return {
    label: 'Requiere revisión',
    note: 'Hay duplicados, costos incompletos o conflictos que impiden certificar el resultado.',
    tone: 'coral' as const,
    classes: 'border-coral/30 bg-coral/[0.07]',
  }
}

type CertificationBlocker = {
  key: string
  label: string
  detail: string
  cta?: { to: string; label: string; state?: Record<string, unknown> }
}

/** Traduce el "por qué" de una confianza baja a problemas concretos, cada uno
 * con el lugar donde resolverlo. Sin inventar datos: solo explica y guía. */
function certificationBlockers(analysis: BusinessAnalysis): CertificationBlocker[] {
  const { alcance, estado_resultados: result, calidad } = analysis
  const blockers: CertificationBlocker[] = []

  if (alcance.documentos_repetidos > 0) {
    blockers.push({
      key: 'duplicados',
      label: `${formatNumber(alcance.documentos_repetidos)} documento(s) con ID repetido`,
      detail: 'Son filas que comparten el mismo N° de documento pero NO son copias exactas — por eso la limpieza de "duplicados exactos" no las quita. Suelen ser el mismo documento cargado desde fuentes distintas, o un ID reutilizado con datos diferentes. Se resuelven por clave de negocio, no como duplicado exacto.',
      cta: { to: '/limpieza?revision=1', label: 'Revisar IDs repetidos' },
    })
  }
  if (alcance.documentos_conflictivos > 0) {
    blockers.push({
      key: 'conflictos',
      label: `${formatNumber(alcance.documentos_conflictivos)} documento(s) en conflicto`,
      detail: 'Un mismo documento trae datos que no coinciden entre filas (montos o fechas distintas). Hay que decidir cuál es la versión válida.',
      cta: { to: '/limpieza?revision=1', label: 'Revisar conflictos' },
    })
  }
  const coverage = result.cobertura_costos_certificable_pct
  if (coverage != null && coverage < 95) {
    blockers.push({
      key: 'costos',
      label: `Costos incompletos — ${formatNumber(coverage)}% de las ventas con costo`,
      detail: 'El resto de las ventas no tiene un costo relacionado, así que la utilidad y el margen salen de una base parcial. Relaciona la hoja de costos o productos, o asigna la columna de costo.',
      cta: { to: '/limpieza', label: 'Asignar costos', state: { openMapping: true, highlightRole: 'costo' } },
    })
  }
  const negativos = numeric(calidad.costos.negativos)
  if (negativos > 0) {
    blockers.push({
      key: 'costos_negativos',
      label: `${formatNumber(negativos)} costo(s) negativo(s)`,
      detail: 'Hay costos con valor negativo que distorsionan la utilidad. Conviene corregirlos en el archivo o en la limpieza.',
      cta: { to: '/limpieza?revision=1', label: 'Revisar costos' },
    })
  }
  if (calidad.filas_inconsistentes_formula > 0) {
    blockers.push({
      key: 'formula',
      label: `${formatNumber(calidad.filas_inconsistentes_formula)} fila(s) con fórmula que no cuadra`,
      detail: 'En esas filas, cantidad × precio no coincide con el total declarado. Conviene revisar esos registros.',
    })
  }
  if (calidad.referencias_problematicas > 0) {
    blockers.push({
      key: 'referencias',
      label: `${formatNumber(calidad.referencias_problematicas)} referencia(s) problemática(s)`,
      detail: 'Algunas filas apuntan a un producto o cliente que no existe en su tabla; quedan fuera del enriquecimiento.',
    })
  }
  return blockers
}

function blockerLocations(analysis: BusinessAnalysis, key: string): string[] {
  if (key === 'duplicados' || key === 'conflictos') {
    return (analysis.calidad.documentos ?? [])
      .filter((item) => key !== 'conflictos' || item.tipo === 'conflicto')
      .slice(0, 6)
      .map((item) => (
        `ID ${item.id}: ${item.ubicaciones.map((place) => `${place.hoja}, fila ${place.fila}`).join(' · ')}`
      ))
  }
  if (key === 'costos_negativos') {
    return (analysis.calidad.costos_detalle?.negativos ?? [])
      .slice(0, 8)
      .map((item) => (
        `${item.hoja ?? 'Hoja de costos'}, fila ${item.fila}: ${formatCLP(item.valor)}${
          item.clave ? ` · clave ${item.clave}` : ''
        }`
      ))
  }
  if (key === 'formula') {
    return analysis.calidad.controles_formula
      .filter((control) => control.filas_inconsistentes > 0)
      .slice(0, 8)
      .map((control) => (
        `${control.hoja}, ${control.control}: filas ${control.filas_ejemplo.join(', ')}`
      ))
  }
  if (key === 'referencias') {
    return analysis.calidad.integridad_referencial
      .filter((relation) => relation.huerfanas > 0 || relation.sin_clave > 0)
      .slice(0, 8)
      .map((relation) => {
        const locations = (relation.ubicaciones ?? [])
          .slice(0, 4)
          .map((place) => `${place.hoja}, fila ${place.fila}`)
          .join(' · ')
        return `${relation.relacion}: ${formatNumber(relation.huerfanas)} huérfanas${
          locations ? ` · ${locations}` : ` · ejemplos ${relation.ejemplos.join(', ')}`
        }`
      })
  }
  return []
}

/** Diagnóstico del análisis cruzado. Vive en Limpieza porque orienta la
 * revisión de datos; Resumen queda reservado para indicadores del negocio. */
export function BusinessQualityPanel({ analysis }: { analysis: BusinessAnalysis }) {
  const certification = certificationMeta(analysis.estado_certificacion)
  const blockers = certificationBlockers(analysis)
  return (
    <section className={`rounded-lg border px-4 py-4 ${certification.classes}`}>
      <div className="flex items-start gap-3">
        {analysis.estado_certificacion === 'certified' ? (
          <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-green" />
        ) : (
          <AlertTriangle className={`mt-0.5 h-5 w-5 shrink-0 ${analysis.estado_certificacion === 'blocked' ? 'text-coral' : 'text-gold'}`} />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-navy">Calidad del análisis relacionado</h2>
            <Badge tone={certification.tone}>{certification.label}</Badge>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-navy/65">
            {certification.note} Confianza técnica: {formatNumber(analysis.confianza_pct)}%.
            Los hallazgos se muestran para revisión; no se borran ni corrigen automáticamente.
          </p>
        </div>
      </div>
      {blockers.length > 0 && (
        <ul className="mt-4 grid gap-3 lg:grid-cols-2">
          {blockers.map((blocker) => {
            const locations = blockerLocations(analysis, blocker.key)
            return (
              <li key={blocker.key} className="rounded-lg border border-navy/10 bg-white/80 p-3">
                <p className="text-xs font-semibold text-navy">{blocker.label}</p>
                <p className="mt-1 text-[11px] leading-relaxed text-navy/60">{blocker.detail}</p>
                {locations.length > 0 && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-[11px] font-semibold text-teal">
                      Ver hojas y filas de ejemplo
                    </summary>
                    <ul className="mt-2 space-y-1 text-[11px] text-navy/65">
                      {locations.map((location) => <li key={location}>{location}</li>)}
                    </ul>
                  </details>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function BusinessTooltip({
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
      {payload.map((item) => (
        <p key={item.name} className="flex items-center justify-between gap-4 text-navy/70">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
            {item.name}
          </span>
          <strong className="text-navy">{formatCLP(item.value)}</strong>
        </p>
      ))}
    </div>
  )
}

function ExecutiveSummary({ analysis }: { analysis: BusinessAnalysis }) {
  const result = analysis.estado_resultados
  const operation = analysis.operacion
  const usesEstimatedCosts = result.costo_venta_estimado_catalogo > 0
  const cards = [
    {
      label: analysis.alcance.documentos_repetidos > 0 ? 'Ventas verificables' : 'Ventas observadas',
      value: money(
        analysis.alcance.documentos_repetidos > 0
          ? result.ventas_certificables
          : result.ventas_observadas,
      ),
      detail: analysis.alcance.documentos_repetidos > 0
        ? `${money(result.ventas_observadas)} observado antes de resolver IDs repetidos`
        : `${formatNumber(analysis.alcance.filas_indicadores)} filas incluidas`,
      icon: CircleDollarSign,
      color: CHART.ingresos,
    },
    {
      label: usesEstimatedCosts ? 'Utilidad bruta estimada' : 'Utilidad bruta conocida',
      value: money(result.utilidad_bruta),
      detail: usesEstimatedCosts
        ? `${percent(result.cobertura_costos_pct)} relacionado; ${percent(result.cobertura_costos_historica_pct)} histórico`
        : `${percent(result.cobertura_costos_pct)} de cobertura`,
      icon: TrendingUp,
      color: CHART.utilidad,
    },
    {
      label: 'Margen bruto',
      value: percent(result.margen_bruto_pct),
      detail: 'solo ventas con costo relacionado',
      icon: Scale,
      color: CHART.flujo,
    },
    {
      label: 'Resultado operacional',
      value: money(result.resultado_operacional),
      detail: result.margen_operacional_pct == null
        ? 'sin ventas, costos y gastos comparables suficientes'
        : `ventas − costo de venta − gastos operacionales · margen ${percent(result.margen_operacional_pct)}`,
      icon: Wallet,
      color: CHART.alerta,
    },
    {
      label: 'Cobrado aplicado',
      value: money(operation.cobrado_aplicado),
      detail: operation.cobranza_sobre_documentos_pct == null
        ? 'sin cobranzas relacionables'
        : `${percent(operation.cobranza_sobre_documentos_pct)} de documentos`,
      icon: Receipt,
      color: CHART.gastos,
    },
    {
      label: 'Inventario valorizado',
      value: money(operation.valor_inventario),
      detail: operation.rotacion_inventario_aprox == null
        ? 'corte disponible, sin rotación fiable'
        : `${formatNumber(operation.rotacion_inventario_aprox)}x de rotación aproximada`,
      icon: Package,
      color: CATEGORICAL[3],
    },
  ]
  const availableRatios = analysis.ratios.filter((ratio) => ratio.estado !== 'unavailable')
  const monthlyProfitability = analysis.evolucion
    .filter((row) => row.utilidad_bruta != null)
    .map((row) => ({
      ...row,
      margen_pct:
        row.ventas > 0 && row.utilidad_bruta != null
          ? (row.utilidad_bruta / row.ventas) * 100
          : null,
    }))
  const qualityIssueCount = certificationBlockers(analysis).length

  return (
    <div className="space-y-6">
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        {cards.map(({ label, value, detail, icon: Icon, color }) => (
          <Card
            key={label}
            className="!p-4"
            style={{ background: `linear-gradient(145deg, ${color}16, #ffffff 66%)` }}
          >
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full" style={{ background: `${color}1c` }}>
                <Icon className="h-4 w-4" style={{ color }} />
              </span>
              <p className="text-xs font-medium text-navy/55">{label}</p>
            </div>
            <p className="mt-3 break-words text-xl font-bold leading-tight text-navy">{value}</p>
            <p className="mt-1 text-[11px] leading-relaxed text-navy/50">{detail}</p>
          </Card>
        ))}
      </section>

      {qualityIssueCount > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gold/30 bg-gold/[0.07] px-4 py-3">
          <p className="text-xs leading-relaxed text-navy/70">
            Hay {formatNumber(qualityIssueCount)} tipo(s) de hallazgo pendiente(s) de revisión.
            El detalle con hojas y filas está en Limpieza de datos.
          </p>
          <Link
            to="/limpieza?revision=1"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-teal hover:text-navy"
          >
            Ver detalle <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      )}

      <div data-testid="business-summary-flow" className="columns-1 gap-6 xl:columns-2">
        {analysis.evolucion.length > 0 && (
          <Card className="mb-6 break-inside-avoid">
            <h2 className="text-base font-semibold text-navy">Evolución del negocio</h2>
            <p className="mt-1 text-xs text-navy/55">
              Resultado operacional = ventas − costo de venta relacionado − gastos operacionales del periodo. Los vacíos no se convierten en cero.
            </p>
            <div className="mt-4 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={analysis.evolucion} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
                  <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                  <XAxis dataKey="mes" tickFormatter={formatMonthShort} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 10 }} width={64} axisLine={false} tickLine={false} />
                  <Tooltip content={<BusinessTooltip />} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="ventas" name="Ventas" fill={CHART.ingresos} radius={[3, 3, 0, 0]} maxBarSize={24} fillOpacity={0.85} />
                  <Bar dataKey="costo" name="Costo relacionado" fill={CHART.gastos} radius={[3, 3, 0, 0]} maxBarSize={24} fillOpacity={0.85} />
                  {/* Resultado operacional en coral y más grueso: es la línea clave
                      y debe leerse por encima de las barras de ventas/costo. */}
                  <Line type="monotone" dataKey="resultado_operacional" name="Resultado operacional" stroke={CHART.alerta} strokeWidth={3.25} dot={{ r: 3, strokeWidth: 1.5, stroke: '#ffffff', fill: CHART.alerta }} activeDot={{ r: 5 }} connectNulls={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Card>
        )}

        <Card className="mb-6 break-inside-avoid">
          <div className="flex items-center gap-2">
            <Target className="h-4.5 w-4.5 text-gold" />
            <h2 className="text-base font-semibold text-navy">Metas y punto de equilibrio</h2>
          </div>
          {analysis.metas.disponible && analysis.metas.cumplimiento_pct != null ? (
            <>
              <div className="mt-4 flex items-end justify-between gap-3">
                <div>
                  <p className="text-xs text-navy/50">Cumplimiento de ventas</p>
                  <p className="text-3xl font-bold text-navy">{percent(analysis.metas.cumplimiento_pct)}</p>
                </div>
                <p className="text-right text-xs text-navy/55">
                  {money(analysis.metas.venta_comparable)}<br />de {money(analysis.metas.meta_venta)}
                </p>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-navy/10">
                <div
                  className="h-full rounded-full bg-gold"
                  style={{ width: `${Math.min(Math.max(analysis.metas.cumplimiento_pct, 0), 100)}%` }}
                />
              </div>
            </>
          ) : (
            <p className="mt-4 text-sm text-navy/55">No hay metas mensuales comparables en el libro.</p>
          )}
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg bg-navy/[0.04] px-3 py-3">
              <p className="text-[11px] text-navy/50">Punto de equilibrio mensual</p>
              <p className="mt-1 text-sm font-semibold text-navy">{money(operation.punto_equilibrio_ventas)}</p>
            </div>
            <div className="rounded-lg bg-teal/[0.06] px-3 py-3">
              <p className="text-[11px] text-navy/50">Gasto fijo mensual promedio</p>
              <p className="mt-1 text-sm font-semibold text-navy">{money(operation.gasto_fijo_mensual_promedio)}</p>
            </div>
          </div>
        </Card>

        <Card className="mb-6 break-inside-avoid">
          <div className="flex items-center gap-2">
            <Calculator className="h-4.5 w-4.5 text-teal" />
            <h2 className="text-base font-semibold text-navy">Indicadores disponibles</h2>
          </div>
          <ul className="mt-3 divide-y divide-navy/5">
            {availableRatios.map((ratio) => (
              <li key={ratio.id} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-navy">{ratio.nombre}</p>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-navy/50">{ratio.nota}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-sm font-bold text-navy">{formatRatioValue(ratio.id, ratio.valor)}</p>
                  <Badge tone={ratio.estado === 'available' ? 'green' : 'gold'}>
                    {ratio.estado === 'available' ? 'Disponible' : 'Parcial'}
                  </Badge>
                </div>
              </li>
            ))}
          </ul>
          {availableRatios.length === 0 && (
            <p className="mt-3 text-sm text-navy/55">No hay ratios con base suficiente.</p>
          )}
        </Card>

        <Card className="mb-6 break-inside-avoid">
          <h2 className="text-base font-semibold text-navy">Utilidad y margen mensual</h2>
          <p className="mt-1 text-xs text-navy/55">
            Compara cuánto quedó después del costo de venta y qué porcentaje representa sobre las ventas relacionadas.
          </p>
          {monthlyProfitability.length > 0 ? (
            <div className="mt-4 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={monthlyProfitability} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                  <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                  <XAxis dataKey="mes" tickFormatter={formatMonthShort} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis yAxisId="money" tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 10 }} width={64} axisLine={false} tickLine={false} />
                  <YAxis yAxisId="margin" orientation="right" tickFormatter={(value) => `${formatNumber(value)}%`} tick={{ fill: AXIS_INK, fontSize: 10 }} width={42} axisLine={false} tickLine={false} />
                  <Tooltip
                    formatter={(value, name) => (
                      name === 'Margen bruto'
                        ? `${formatNumber(Number(value))}%`
                        : formatCLP(Number(value))
                    )}
                    labelFormatter={(label) => formatMonthShort(String(label))}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <ReferenceLine yAxisId="money" y={0} stroke={AXIS_INK} strokeOpacity={0.45} />
                  <Bar yAxisId="money" dataKey="utilidad_bruta" name="Utilidad bruta" fill={CHART.utilidad} radius={[4, 4, 0, 0]} maxBarSize={36} />
                  <Line yAxisId="margin" type="monotone" dataKey="margen_pct" name="Margen bruto" stroke={CHART.flujo} strokeWidth={2.5} dot={{ r: 3 }} connectNulls={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="mt-4 text-sm text-navy/55">No hay costos relacionados suficientes para calcular utilidad mensual.</p>
          )}
        </Card>
      </div>
    </div>
  )
}

function formatRatioValue(id: string, value: number | null) {
  if (value == null) return 'No disponible'
  if (id.includes('margen') || id.includes('tasa') || id.includes('cumplimiento')) {
    return percent(value)
  }
  if (id.includes('rotacion')) return `${formatNumber(value)}x`
  return money(value)
}

function ProfitabilityChart({ rows }: { rows: BusinessGroupRow[] }) {
  const data = rows
    .filter((row) => row.utilidad != null)
    .slice(0, 10)
    .map((row) => ({ ...row, etiqueta: truncateLabel(row.nombre, 20) }))
  if (!data.length) return <p className="mt-4 text-sm text-navy/55">No hay cobertura suficiente para comparar utilidad.</p>
  return (
    <div className="mt-4" style={{ height: Math.max(280, data.length * 36 + 48) }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 8 }}>
          <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
          <XAxis type="number" tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey="etiqueta" width={130} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
          <Tooltip formatter={(value) => formatCLP(Number(value))} />
          <ReferenceLine x={0} stroke={AXIS_INK} />
          <Bar dataKey="utilidad" name="Utilidad conocida" fill={CHART.utilidad} radius={[0, 3, 3, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function DiagnosticAnalysis({ analysis }: { analysis: BusinessAnalysis }) {
  const costQuality = analysis.calidad.costos
  const problematicCosts = numeric(costQuality.negativos) + numeric(costQuality.ceros) + numeric(costQuality.extremos)
  const sensitivityRows = [
    { escenario: 'Costo actual', utilidad: analysis.sensibilidad.base_utilidad_bruta },
    { escenario: 'Costo +5%', utilidad: analysis.sensibilidad.costo_mas_5 },
    { escenario: 'Costo +10%', utilidad: analysis.sensibilidad.costo_mas_10 },
  ].filter((row): row is { escenario: string; utilidad: number } => row.utilidad != null)
  const products = analysis.agrupaciones.productos ?? []
  const unavailable = analysis.ratios.filter((ratio) => ratio.estado === 'unavailable')

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-navy/15 bg-navy/[0.035] px-4 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-navy/45">Explorar · entender causas</p>
        <p className="mt-1 text-sm text-navy/70">
          Aquí no repetimos el tablero: explicamos qué limita el resultado, dónde se concentra y qué decisión revisar primero.
        </p>
      </section>

      <section>
        <div className="flex items-center gap-2">
          <CircleHelp className="h-5 w-5 text-gold" />
          <h2 className="text-lg font-semibold text-navy">Qué requiere tu atención</h2>
        </div>
        {analysis.decisiones.length > 0 ? (
          <div className="mt-4 columns-1 gap-4 lg:columns-2">
            {analysis.decisiones.map((decision) => {
              const high = decision.severidad === 'alta'
              return (
                <article
                  key={decision.titulo}
                  className={`mb-4 break-inside-avoid rounded-lg border p-4 ${high ? 'border-coral/30 bg-coral/[0.055]' : 'border-gold/30 bg-gold/[0.06]'}`}
                >
                  <div className="flex items-start gap-3">
                    <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${high ? 'bg-coral/10 text-coral' : 'bg-gold/15 text-gold'}`}>
                      <AlertTriangle className="h-4 w-4" />
                    </span>
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-semibold text-navy">{decision.titulo}</h3>
                        <Badge tone={high ? 'coral' : 'gold'}>{decision.severidad}</Badge>
                      </div>
                      <p className="mt-2 text-xs leading-relaxed text-navy/65"><strong>Evidencia:</strong> {decision.evidencia}</p>
                      <p className="mt-2 text-xs leading-relaxed text-navy/80"><strong>Acción:</strong> {decision.accion}</p>
                      <p className="mt-2 text-[10px] text-navy/40">Confianza de la señal: {formatNumber(decision.confianza * 100)}%</p>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        ) : (
          <p className="mt-3 text-sm text-navy/55">No se detectaron decisiones urgentes con la información disponible.</p>
        )}
      </section>

      <div className="grid items-start gap-6 xl:grid-cols-2">
        <Card className="min-w-0">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4.5 w-4.5 text-green" />
            <h2 className="text-base font-semibold text-navy">Qué productos explican la utilidad</h2>
          </div>
          <p className="mt-1 text-xs text-navy/55">Comparación sobre ventas con costo relacionado, sin rellenar faltantes con cero.</p>
          <ProfitabilityChart rows={products} />
        </Card>

        <Card className="min-w-0">
          <div className="flex items-center gap-2">
            <Scale className="h-4.5 w-4.5 text-coral" />
            <h2 className="text-base font-semibold text-navy">Sensibilidad al costo</h2>
          </div>
          <p className="mt-1 text-xs text-navy/55">Impacto mecánico si el costo conocido sube y ventas/volumen permanecen iguales.</p>
          {sensitivityRows.length > 0 ? (
            <div className="mt-4 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sensitivityRows} margin={{ top: 12, right: 12, bottom: 4, left: 8 }}>
                  <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                  <XAxis dataKey="escenario" tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 10 }} width={64} axisLine={false} tickLine={false} />
                  <Tooltip formatter={(value) => formatCLP(Number(value))} />
                  <ReferenceLine y={0} stroke={AXIS_INK} />
                  <Bar dataKey="utilidad" name="Utilidad bruta" fill={CHART.alerta} radius={[4, 4, 0, 0]} maxBarSize={52} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="mt-4 text-sm text-navy/55">No hay costo pareado suficiente para simular escenarios.</p>
          )}
          <p className="mt-2 text-[11px] leading-relaxed text-navy/45">{analysis.sensibilidad.nota}</p>
        </Card>
      </div>

      <section className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(300px,.75fr)]">
        <Card className="min-w-0">
          <div className="flex items-center gap-2">
            <Link2 className="h-4.5 w-4.5 text-teal" />
            <h2 className="text-base font-semibold text-navy">Calidad de las relaciones</h2>
          </div>
          <p className="mt-1 text-xs text-navy/55">Una referencia huérfana queda fuera del enriquecimiento; nunca multiplica ventas ni se une a ciegas.</p>
          <div className="mt-4 space-y-3 sm:hidden">
            {analysis.calidad.integridad_referencial.map((row) => (
              <div key={row.relacion} className="rounded-lg bg-navy/[0.04] px-3 py-3 text-xs">
                <p className="font-semibold text-navy">{row.relacion}</p>
                <p className="mt-1 text-navy/60">Cobertura {percent(row.cobertura_pct)} · {formatNumber(row.huerfanas)} huérfanas · {formatNumber(row.sin_clave)} sin clave</p>
              </div>
            ))}
          </div>
          <div className="mt-4 hidden overflow-x-auto sm:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-navy/10 text-left text-[11px] uppercase text-navy/45">
                  <th className="pb-2 pr-4">Relación</th>
                  <th className="pb-2 pr-4 text-right">Cobertura</th>
                  <th className="pb-2 pr-4 text-right">Huérfanas</th>
                  <th className="pb-2 text-right">Sin clave</th>
                </tr>
              </thead>
              <tbody>
                {analysis.calidad.integridad_referencial.map((row) => (
                  <tr key={row.relacion} className="border-b border-navy/5">
                    <td className="py-2.5 pr-4 font-medium text-navy">{row.relacion}</td>
                    <td className="py-2.5 pr-4 text-right text-navy/70">{percent(row.cobertura_pct)}</td>
                    <td className="py-2.5 pr-4 text-right text-navy/70">{formatNumber(row.huerfanas)}</td>
                    <td className="py-2.5 text-right text-navy/70">{formatNumber(row.sin_clave)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <div className="space-y-6">
          <Card>
            <h2 className="text-base font-semibold text-navy">Controles de calidad</h2>
            <dl className="mt-3 space-y-3 text-sm">
              <QualityLine label="Referencias problemáticas" value={analysis.calidad.referencias_problematicas} />
              <QualityLine label="Fórmulas que no cuadran" value={analysis.calidad.filas_inconsistentes_formula} />
              <QualityLine label="Costos a revisar" value={problematicCosts} />
              <QualityLine label="Documentos sobrepagados" value={analysis.operacion.documentos_sobrepagados} />
              <QualityLine label="Pagos duplicados excluidos" value={analysis.operacion.pagos_duplicados_excluidos} />
            </dl>
          </Card>
          {unavailable.length > 0 && (
            <Card>
              <div className="flex items-center gap-2">
                <Calculator className="h-4.5 w-4.5 text-navy/55" />
                <h2 className="text-base font-semibold text-navy">Qué falta para otros ratios</h2>
              </div>
              <ul className="mt-3 space-y-3">
                {unavailable.map((ratio) => (
                  <li key={ratio.id}>
                    <p className="text-sm font-medium text-navy">{ratio.nombre}</p>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-navy/50">{ratio.nota}</p>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </section>

      {analysis.portafolio.productos.length > 0 && (
        <Card>
          <h2 className="text-base font-semibold text-navy">Portafolio: volumen y margen</h2>
          <p className="mt-1 text-xs text-navy/55">Clasificación relativa frente a las medianas del propio archivo.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {(['estrella', 'vaca_lechera', 'oportunidad', 'problema'] as const).map((quadrant, index) => {
              const rows = analysis.portafolio.productos.filter((row) => row.cuadrante === quadrant)
              const labels = {
                estrella: 'Alto volumen y margen',
                vaca_lechera: 'Volumen alto, margen bajo',
                oportunidad: 'Margen alto, volumen bajo',
                problema: 'Volumen y margen bajos',
              }
              return (
                <div key={quadrant} className="rounded-lg border border-navy/10 bg-work px-3 py-3">
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: CATEGORICAL[index] }} />
                    <p className="text-xs font-semibold text-navy">{labels[quadrant]}</p>
                  </div>
                  <p className="mt-1 text-[11px] text-navy/50">{formatNumber(rows.length)} producto(s)</p>
                  <p className="mt-2 line-clamp-3 text-[11px] leading-relaxed text-navy/65">
                    {rows.slice(0, 4).map((row) => row.nombre).join(' · ') || 'Sin productos en este cuadrante'}
                  </p>
                </div>
              )
            })}
          </div>
        </Card>
      )}
    </div>
  )
}

function QualityLine({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-navy/5 pb-2 last:border-0 last:pb-0">
      <dt className="text-navy/65">{label}</dt>
      <dd className={`font-semibold ${value > 0 ? 'text-coral' : 'text-green'}`}>{formatNumber(value)}</dd>
    </div>
  )
}

export default function BusinessAnalysisPanel({
  analysis,
  variant,
}: {
  analysis: BusinessAnalysis
  variant: Variant
}) {
  return variant === 'summary'
    ? <ExecutiveSummary analysis={analysis} />
    : <DiagnosticAnalysis analysis={analysis} />
}
