import { AlertTriangle, Info } from 'lucide-react'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import Card from '../ui/Card'
import {
  AXIS_INK,
  CHART,
  GRID_STROKE,
  chartColorForKey,
  buildRobustHeatScale,
  formatCLPCompact,
  formatMonthShort,
  prepareCategoricalChart,
  robustHeatIntensity,
  truncateLabel,
  type CategoricalChartSourceRow,
  type PreparedCategoricalChart,
} from '../../lib/charts'
import { formatCLP, formatNumber } from '../../lib/format'
import type { MetricsResult } from '../../lib/types'
import {
  analyticalFingerprint,
  MAX_SUMMARY_CHARTS,
  selectUniqueVisualizations,
} from '../../lib/visualizationRegistry'

interface CategoricalChartCardProps {
  title: string
  subtitle: string
  dimension: string
  rows: CategoricalChartSourceRow[]
  totalGroups?: number
  totalValue?: number
  cumulative?: boolean
  outOfRange?: { filas: number; monto_asociado: number }
}

function rowDetail(value: number, share: number): string {
  return `${formatCLPCompact(value)} · ${formatNumber(Math.round(share * 10) / 10)}%`
}

function StackedComposition({ chart }: { chart: PreparedCategoricalChart }) {
  const denominator = chart.rows.reduce((sum, row) => sum + Math.max(row.participacion, 0), 0) || 1
  return (
    <div className="mt-5" data-chart-kind="stacked-100">
      <div
        className="flex h-10 w-full overflow-hidden rounded-lg bg-navy/[0.06]"
        role="img"
        aria-label={chart.rows.map((row) => `${row.nombre}: ${formatNumber(row.participacion)}%`).join(', ')}
      >
        {chart.rows.map((row) => {
          const width = Math.max(row.participacion, 0) / denominator * 100
          return (
            <div
              key={row.nombre}
              className="flex min-w-0 items-center justify-center border-r border-white/70 px-1 text-[10px] font-semibold text-white last:border-r-0"
              style={{ width: `${width}%`, background: chartColorForKey(row.nombre) }}
              title={`${row.nombre}: ${rowDetail(row.ingresos, row.participacion)}`}
            >
              {width >= 15 ? `${formatNumber(row.participacion)}%` : ''}
            </div>
          )
        })}
      </div>
      <ul className="mt-4 space-y-2">
        {chart.rows.map((row) => (
          <li key={row.nombre} className="flex items-center justify-between gap-3 text-xs">
            <span className="flex min-w-0 items-center gap-2 text-navy/75">
              <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: chartColorForKey(row.nombre) }} />
              <span className="truncate" title={row.nombre}>{row.nombre}</span>
            </span>
            <span className="shrink-0 font-semibold text-navy">{rowDetail(row.ingresos, row.participacion)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function ConcentrationNotice({ chart }: { chart: PreparedCategoricalChart }) {
  const dominant = chart.rows.reduce((current, row) => (
    row.participacion > current.participacion ? row : current
  ))
  return (
    <div
      className="mt-5 rounded-xl border border-gold/40 bg-gold/[0.08] p-4"
      data-chart-kind="concentration"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-gold" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-navy">Concentración muy alta</p>
          <p className="mt-1 text-sm leading-relaxed text-navy/70">
            <strong>{dominant.nombre}</strong> concentra{' '}
            <strong>{formatNumber(dominant.participacion)}%</strong> del monto visible
            ({formatCLP(dominant.ingresos)}). La advertencia reemplaza el gráfico para no exagerar una diferencia ya evidente.
          </p>
        </div>
      </div>
    </div>
  )
}

function HorizontalBars({ chart, color }: { chart: PreparedCategoricalChart; color: string }) {
  const rows = chart.rows.map((row) => ({
    ...row,
    detalle: rowDetail(row.ingresos, row.participacion),
  }))
  const maximum = Math.max(...rows.map((row) => Math.abs(row.ingresos)), 1)
  return (
    <div className="mt-5 space-y-4" data-chart-kind="bars">
      {rows.map((row) => (
        <div key={row.nombre} className="min-w-0">
          <div className="flex items-end justify-between gap-3 text-xs">
            <span className="min-w-0 truncate font-medium text-navy/75" title={row.nombre}>{row.nombre}</span>
            <span className="shrink-0 whitespace-nowrap font-semibold text-navy">{row.detalle}</span>
          </div>
          <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-navy/[0.07]">
            <div
              className="h-full min-w-0 rounded-full"
              style={{
                width: `${Math.max(Math.abs(row.ingresos) / maximum * 100, row.ingresos === 0 ? 0 : 1.5)}%`,
                background: row.ingresos < 0 ? CHART.alerta : color,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

function NaturalBars({ chart, color }: { chart: PreparedCategoricalChart; color: string }) {
  const rows = chart.rows.map((row) => ({
    ...row,
    etiqueta: truncateLabel(row.nombre, 15),
    detalle: `${formatNumber(row.participacion)}%`,
  }))
  return (
    <div className="mt-4 overflow-x-auto" data-chart-kind="natural-bars">
      <div style={{ height: Math.min(260, Math.max(190, rows.length * 18 + 130)), minWidth: Math.max(rows.length * 88, 440) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 28, right: 12, bottom: 10, left: 8 }}>
            <CartesianGrid stroke={GRID_STROKE} vertical={false} />
            <XAxis dataKey="etiqueta" tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={{ stroke: GRID_STROKE }} tickLine={false} />
            <YAxis tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} width={58} />
            <Tooltip formatter={(value) => formatCLP(Number(value))} />
            <Bar dataKey="ingresos" name="Ventas netas" fill={color} radius={[4, 4, 0, 0]} isAnimationActive={false}>
              <LabelList dataKey="detalle" position="top" fill={AXIS_INK} fontSize={10} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-navy/60">
        {rows.map((row) => (
          <li key={row.nombre}><strong className="text-navy/80">{row.nombre}:</strong> {formatCLP(row.ingresos)} · {formatNumber(row.participacion)}%</li>
        ))}
      </ul>
    </div>
  )
}

function CompactChartGrid({
  children,
  testId,
}: {
  children: ReactNode
  testId?: string
}) {
  return (
    <div
      data-testid={testId}
      className="columns-1 gap-6 md:columns-2 2xl:columns-3 [&>*]:mb-6 [&>*]:break-inside-avoid"
    >
      {children}
    </div>
  )
}

function ParetoChart({ chart, color }: { chart: PreparedCategoricalChart; color: string }) {
  const rows = chart.rows.map((row) => ({
    ...row,
    etiqueta: truncateLabel(row.nombre, 16),
    detalle: rowDetail(row.ingresos, row.participacion),
  }))
  return (
    <div className="mt-4" data-chart-kind="pareto">
      <div style={{ height: Math.max(rows.length * 28 + 56, 250) }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} layout="vertical" margin={{ top: 22, right: 8, bottom: 4, left: 2 }}>
          <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
          <XAxis xAxisId="amount" type="number" hide />
          <XAxis
            xAxisId="share"
            type="number"
            orientation="top"
            domain={[0, 100]}
            ticks={[0, 25, 50, 75, 100]}
            tickFormatter={(value) => `${value}%`}
            tick={{ fill: AXIS_INK, fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis type="category" dataKey="etiqueta" width={96} tick={{ fill: AXIS_INK, fontSize: 9 }} axisLine={false} tickLine={false} />
          <Tooltip formatter={(value, name) => name === 'Acumulado' ? `${formatNumber(Number(value))}%` : formatCLP(Number(value))} />
          <Bar xAxisId="amount" dataKey="ingresos" name="Ventas netas" fill={color} radius={[0, 4, 4, 0]} isAnimationActive={false}>
          </Bar>
          <Line xAxisId="share" dataKey="acumulado" name="Acumulado" stroke={CHART.gastos} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-2 space-y-1.5 border-t border-navy/[0.06] pt-3 text-[11px]">
        {rows.map((row) => (
          <li key={row.nombre} className="flex items-start justify-between gap-3">
            <span className="min-w-0 truncate text-navy/65" title={row.nombre}>{row.nombre}</span>
            <span className="shrink-0 whitespace-nowrap font-semibold text-navy/80">{row.detalle}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function CategoricalChartCard({
  title,
  subtitle,
  dimension,
  rows,
  totalGroups,
  totalValue,
  cumulative = false,
  outOfRange,
}: CategoricalChartCardProps) {
  const chart = prepareCategoricalChart(rows, {
    dimension,
    cumulative,
    totalGroups,
    totalValue,
  })
  if (!chart.rows.length) return null
  const color = chartColorForKey(dimension)
  return (
    <Card className="min-w-0" style={{ background: `linear-gradient(145deg, ${color}0b, #ffffff 42%)` }}>
      <div className="flex items-center gap-2">
        <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: color }} />
        <h3 className="min-w-0 text-base font-semibold text-navy">{title}</h3>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-navy/55">
        {subtitle}
        {chart.groupedCount > 0 ? ` Se agruparon ${chart.groupedCount} categorías en «Otros».` : ''}
      </p>
      {outOfRange && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-gold/35 bg-gold/[0.08] px-3 py-2 text-xs text-navy/70">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-gold" />
          <span className="min-w-0 flex-1">
            <strong>{formatNumber(outOfRange.filas)}</strong> filas fuera de 0–100% · monto asociado: <strong>{formatCLP(outOfRange.monto_asociado)}</strong>.
          </span>
          <Link to="/limpieza?revision=1" className="font-semibold text-teal hover:underline">Revisar</Link>
        </div>
      )}
      {chart.kind === 'concentration' ? <ConcentrationNotice chart={chart} /> : null}
      {chart.kind === 'stacked-100' ? <StackedComposition chart={chart} /> : null}
      {chart.kind === 'bars' ? <HorizontalBars chart={chart} color={color} /> : null}
      {chart.kind === 'natural-bars' ? <NaturalBars chart={chart} color={color} /> : null}
      {chart.kind === 'pareto' ? <ParetoChart chart={chart} color={color} /> : null}
      {chart.groupedCount > 0 && (
        <div className="mt-3 border-t border-navy/10 pt-3 text-right">
          <Link to="/explorar" className="text-xs font-semibold text-teal hover:underline">
            Ver detalle completo en Explorar datos
          </Link>
        </div>
      )}
    </Card>
  )
}

function TicketHistogram({ distribution }: { distribution: NonNullable<MetricsResult['distribucion_montos']> }) {
  const rows = distribution.bins.map((bin) => ({
    ...bin,
    rango: `${formatCLPCompact(bin.desde)}–${formatCLPCompact(bin.hasta)}`,
  }))
  return (
    <Card className="min-w-0">
      <h3 className="text-base font-semibold text-navy">
        Distribución de venta por {distribution.granularidad === 'linea' ? 'línea' : 'registro'}
      </h3>
      <p className="mt-1 text-xs text-navy/55">Cantidad de observaciones por tramo de monto; permite ver dispersión y valores extremos.</p>
      <div className="mt-4 h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 28, left: 4 }}>
            <CartesianGrid stroke={GRID_STROKE} vertical={false} />
            <XAxis dataKey="rango" interval="preserveStartEnd" angle={-25} textAnchor="end" tick={{ fill: AXIS_INK, fontSize: 9 }} axisLine={{ stroke: GRID_STROKE }} tickLine={false} />
            <YAxis allowDecimals={false} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} width={42} />
            <Tooltip formatter={(value) => `${formatNumber(Number(value))} registros`} />
            <Bar dataKey="registros" name="Registros" fill={CHART.flujo} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function MonthDimensionHeatmap({ matrix }: { matrix: NonNullable<MetricsResult['matriz_mes_dimension']> }) {
  const [displayMode, setDisplayMode] = useState<'amount' | 'share'>('amount')
  const values = new Map(matrix.valores.map((row) => [`${row.nombre}\u0000${row.mes}`, row.ingresos]))
  const monthTotals = new Map<string, number>()
  matrix.valores.forEach((row) => {
    monthTotals.set(row.mes, (monthTotals.get(row.mes) ?? 0) + Math.abs(row.ingresos))
  })
  const displayedValues = matrix.valores.map((row) => (
    displayMode === 'share'
      ? Math.abs(row.ingresos) / Math.max(monthTotals.get(row.mes) ?? 0, 1) * 100
      : row.ingresos
  ))
  const scale = buildRobustHeatScale(displayedValues)
  const title = matrix.dimension.charAt(0).toUpperCase() + matrix.dimension.slice(1)
  const columns = `140px repeat(${matrix.meses.length}, minmax(76px, 1fr))`
  const scaleLabel = (value: number) => displayMode === 'share'
    ? `${formatNumber(value)}%`
    : formatCLPCompact(value)
  return (
    <Card className="min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-navy">Mes × {title}</h3>
          <p className="mt-1 text-xs text-navy/55">La intensidad muestra dónde se concentra la venta en el tiempo usando «{matrix.columna}».</p>
        </div>
        <div className="inline-flex rounded-lg border border-navy/10 bg-navy/[0.03] p-0.5 text-[10px] font-semibold">
          <button type="button" aria-pressed={displayMode === 'amount'} onClick={() => setDisplayMode('amount')} className={`rounded-md px-2 py-1 ${displayMode === 'amount' ? 'bg-white text-teal shadow-sm' : 'text-navy/55'}`}>Monto</button>
          <button type="button" aria-pressed={displayMode === 'share'} onClick={() => setDisplayMode('share')} className={`rounded-md px-2 py-1 ${displayMode === 'share' ? 'bg-white text-teal shadow-sm' : 'text-navy/55'}`}>Participación</button>
        </div>
      </div>
      <div className="mt-4 overflow-x-auto">
        <div className="grid gap-1.5" style={{ gridTemplateColumns: columns, minWidth: 140 + matrix.meses.length * 82 }}>
          <div />
          {matrix.meses.map((month) => (
            <div key={month} className="px-1 pb-1 text-center text-[10px] font-semibold text-navy/55">{formatMonthShort(month)}</div>
          ))}
          {matrix.grupos.flatMap((group) => [
            <div key={`${group}-label`} className="flex items-center truncate pr-2 text-xs font-medium text-navy/70" title={group}>{group}</div>,
            ...matrix.meses.map((month) => {
              const value = values.get(`${group}\u0000${month}`) ?? 0
              const displayed = displayMode === 'share'
                ? Math.abs(value) / Math.max(monthTotals.get(month) ?? 0, 1) * 100
                : value
              const ratio = robustHeatIntensity(displayed, scale)
              const negative = value < 0
              const outlier = Math.abs(displayed) > scale.reference
              const background = negative
                ? `rgba(212, 80, 43, ${0.10 + ratio * 0.78})`
                : `rgba(0, 163, 163, ${0.08 + ratio * 0.80})`
              return (
                <div
                  key={`${group}-${month}`}
                  className={`flex h-10 items-center justify-center rounded-md px-1 text-center text-[10px] font-semibold ${outlier ? 'ring-2 ring-gold/70 ring-offset-1' : ''}`}
                  style={{ background, color: ratio > 0.52 ? '#ffffff' : '#1f3547' }}
                  title={`${group} · ${formatMonthShort(month)}: ${formatCLP(value)} · ${formatNumber(Math.abs(value) / Math.max(monthTotals.get(month) ?? 0, 1) * 100)}% del mes${outlier ? ' · valor extremo' : ''}`}
                >
                  {value === 0 ? '—' : displayMode === 'share' ? `${formatNumber(displayed)}%` : formatCLPCompact(value)}
                </div>
              )
            }),
          ])}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-navy/55" aria-label="Escala del mapa de calor">
        <span>Bajo {scaleLabel(scale.minimum)}</span>
        <span className="h-2.5 w-24 rounded-full bg-gradient-to-r from-teal/10 to-teal" aria-hidden />
        <span>Referencia p95 {scaleLabel(scale.reference)}</span>
        <span>Máximo {scaleLabel(scale.maximum)}</span>
        {scale.logarithmic ? <span className="font-semibold text-gold">Escala logarítmica</span> : null}
        {scale.maximum > scale.reference ? <span className="font-semibold text-gold">Anillo = valor extremo</span> : null}
      </div>
    </Card>
  )
}

function sectionTitle(title: string, subtitle: string) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-navy">{title}</h2>
      <p className="mt-0.5 text-xs text-navy/50">{subtitle}</p>
    </div>
  )
}

function flexiblePriority(column: string): number {
  const value = column.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es-CL').replace(/_/g, ' ')
  if (value.includes('medio') || value.includes('pago') || value.includes('forma')) return 0
  if (value.includes('descuento') || value.includes('dcto')) return 1
  if (value.includes('estado') || value.includes('status')) return 2
  if (value.includes('origen') || value.includes('hoja')) return 3
  return 4
}

export default function AdaptiveSalesCharts({ metrics }: { metrics: MetricsResult }) {
  const channel = metrics.ventas_por_canal ?? []
  const channelLabel = metrics.agrupado_por_canal === 'sucursal' ? 'Sucursal' : 'Canal'
  const products = metrics.top_productos ?? []
  const productTotal = metrics.kpis.ingresos_totales?.valor
  const productGroups = metrics.lideres_productos?.total_productos ?? products.length
  const hasMatrix = Boolean(
    metrics.matriz_mes_dimension
    && metrics.matriz_mes_dimension.meses.length > 1
    && metrics.matriz_mes_dimension.grupos.length > 1,
  )
  const balancedPrimary = channel.length > 0 && products.length > 0 && hasMatrix
  const weekdays = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
  const weekdayByName = new Map((metrics.por_dia_semana ?? []).map((row) => [row.dia, row]))
  const weekdayRows = weekdays.map((day) => ({
    nombre: day.charAt(0).toUpperCase() + day.slice(1),
    ingresos: weekdayByName.get(day)?.ingresos ?? 0,
  }))
  const behaviorCards = [
    metrics.clientes && metrics.clientes.unicos > 1 && metrics.clientes.top.length > 1 ? 'clients' : null,
    (metrics.por_dia_semana ?? []).length > 1 ? 'weekdays' : null,
    metrics.distribucion_montos?.bins.length ? 'histogram' : null,
  ].filter(Boolean)
  const primaryCount = Number(channel.length > 0) + Number(products.length > 0) + Number(hasMatrix)
  const flexibleBudget = Math.max(0, MAX_SUMMARY_CHARTS - primaryCount - behaviorCards.length)
  const flexibleSelection = selectUniqueVisualizations(
    (metrics.agrupaciones_flexibles ?? []).map((group) => ({
      group,
      fingerprint: analyticalFingerprint({
        metric: 'ventas_netas',
        dimension: group.columna,
        granularity: 'categoria',
        calculation: 'observed',
      }),
      priority: 100 - flexiblePriority(group.columna),
      confidence: 'certified' as const,
    })),
    flexibleBudget,
  )
  const flexible = flexibleSelection.selected.map((item) => item.group)

  return (
    <div className="space-y-8">
      {(channel.length > 0 || products.length > 0 || hasMatrix) && (
        <section className="space-y-4" aria-labelledby="summary-commercial-cuts">
          <div id="summary-commercial-cuts">
            {sectionTitle('Quién vende y qué se vende', 'Los dos cortes comerciales de mayor señal disponibles en este archivo.')}
          </div>
          <div data-testid="summary-commercial-grid" className="grid items-start gap-6 lg:grid-cols-2">
            {channel.length > 0 && (
              <div className={balancedPrimary ? 'lg:col-start-1 lg:row-start-1' : ''}>
                <CategoricalChartCard
                  title={`Ventas por ${channelLabel}`}
                  subtitle={`Comparación ordenada por venta neta entre ${channelLabel.toLocaleLowerCase('es-CL')}es.`}
                  dimension={channelLabel}
                  rows={channel}
                  totalGroups={channel.length}
                  totalValue={productTotal}
                />
              </div>
            )}
            {products.length > 0 && (
              <div className={balancedPrimary ? 'lg:col-start-2 lg:row-span-2 lg:row-start-1' : ''}>
                <CategoricalChartCard
                  title="Concentración por producto / servicio"
                  subtitle="Las barras muestran venta neta y la línea el porcentaje acumulado del catálogo."
                  dimension="Producto"
                  rows={products}
                  totalGroups={productGroups}
                  totalValue={productTotal}
                  cumulative
                />
              </div>
            )}
            {hasMatrix && metrics.matriz_mes_dimension && (
              <div className={balancedPrimary ? 'lg:col-start-1 lg:row-start-2' : 'lg:col-span-2'}>
                <MonthDimensionHeatmap matrix={metrics.matriz_mes_dimension} />
              </div>
            )}
          </div>
        </section>
      )}

      {flexible.length > 0 && (
        <section className="space-y-4" aria-labelledby="summary-sales-method">
          <div id="summary-sales-method">
            {sectionTitle('Cómo se vende', 'Cada dimensión usa automáticamente el formato más honesto para su cardinalidad y orden semántico.')}
          </div>
          <CompactChartGrid testId="summary-sales-method-grid">
            {flexible.map((group) => (
              <CategoricalChartCard
                key={group.columna}
                title={`Ventas por ${group.columna}`}
                subtitle={`Ingresos netos según «${group.columna}».`}
                dimension={group.columna}
                rows={group.grupos_completos ?? group.grupos}
                totalGroups={group.grupos_totales}
                totalValue={productTotal}
                outOfRange={group.fuera_de_rango}
              />
            ))}
          </CompactChartGrid>
          {flexibleSelection.omitted > 0 && (
            <p className="text-right text-xs text-navy/55">
              {flexibleSelection.omitted} análisis secundario(s) se omitieron para evitar repeticiones.{' '}
              <Link to="/explorar" className="font-semibold text-teal hover:underline">Verlos en Explorar datos</Link>
            </p>
          )}
        </section>
      )}

      {behaviorCards.length > 0 && (
        <section className="space-y-4" aria-labelledby="summary-sales-behavior">
          <div id="summary-sales-behavior">
            {sectionTitle('Comportamiento y concentración', 'Se muestran únicamente análisis respaldados por columnas presentes en el archivo.')}
          </div>
          <CompactChartGrid testId="summary-sales-behavior-grid">
            {metrics.clientes && metrics.clientes.unicos > 1 && metrics.clientes.top.length > 1 && (
              <CategoricalChartCard
                title="Concentración por cliente"
                subtitle={`Pareto de ${formatNumber(metrics.clientes.unicos)} clientes identificados.`}
                dimension="Cliente"
                rows={metrics.clientes.pareto ?? metrics.clientes.top}
                totalGroups={metrics.clientes.unicos}
                cumulative
              />
            )}
            {(metrics.por_dia_semana ?? []).length > 1 && (
              <CategoricalChartCard
                title="Ventas por día de la semana"
                subtitle="Lunes a domingo en orden natural para apoyar decisiones de dotación y horario."
                dimension="Día de semana"
                rows={weekdayRows}
                totalGroups={7}
                totalValue={productTotal}
              />
            )}
            {metrics.distribucion_montos?.bins.length ? (
              <TicketHistogram distribution={metrics.distribucion_montos} />
            ) : null}
          </CompactChartGrid>
        </section>
      )}

      {!channel.length && !products.length && !flexible.length && behaviorCards.length === 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-navy/10 bg-navy/[0.03] px-4 py-3 text-sm text-navy/60">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          No hay dimensiones categóricas suficientes para construir comparaciones honestas.
        </div>
      )}
    </div>
  )
}
