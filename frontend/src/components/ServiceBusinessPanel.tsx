import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  BriefcaseBusiness,
  CircleDollarSign,
  Clock3,
  Gauge,
  ShieldAlert,
  TrendingUp,
  Wallet,
  Wrench,
} from 'lucide-react'
import type { ReactNode } from 'react'
import Card from './ui/Card'
import { CATEGORICAL, CHART, GRID_STROKE, formatCLPCompact, formatMonthShort } from '../lib/charts'
import { formatCLP, formatNumber } from '../lib/format'
import type { ServiceBusinessAnalysis } from '../lib/types'

const PROFIT_COLOR = '#239469'
const RISK_COLOR = '#ef7657'
const PURPLE = '#8b5cf6'

function moneyTooltip(value: unknown) {
  return typeof value === 'number' ? formatCLP(value) : String(value ?? '')
}

function warningLabel(warning: string) {
  const normalized = warning.toLocaleLowerCase('es')
  if (normalized.includes('parcial')) return 'Periodo parcial. '
  if (normalized.includes('sla')) return 'SLA. '
  return 'Lectura contractual. '
}

function EmptyChart({ message }: { message: string }) {
  return (
    <div className="grid h-full min-h-48 place-items-center rounded-xl border border-dashed border-navy/15 bg-work/30 px-6 text-center">
      <p className="max-w-sm text-xs leading-relaxed text-navy/50">{message}</p>
    </div>
  )
}

function ChartCard({
  title,
  note,
  className = '',
  bodyClassName = 'h-72',
  children,
}: {
  title: string
  note: string
  className?: string
  bodyClassName?: string
  children: ReactNode
}) {
  return (
    <Card className={`min-w-0 ${className}`}>
      <h3 className="text-sm font-semibold text-navy">{title}</h3>
      <p className="mt-1 text-xs leading-relaxed text-navy/55">{note}</p>
      <div className={`mt-4 min-w-0 ${bodyClassName}`}>{children}</div>
    </Card>
  )
}

function waterfallRows(analysis: ServiceBusinessAnalysis) {
  let running = 0
  return analysis.cascada.map((row) => {
    if (row.tipo === 'total' || row.tipo === 'subtotal') {
      running = row.valor
      return {
        ...row,
        base: 0,
        cambio: Math.abs(row.valor),
        resultado: row.valor,
      }
    }
    const next = running + row.valor
    const result = {
      ...row,
      base: Math.min(running, next),
      cambio: Math.abs(row.valor),
      resultado: row.valor,
    }
    running = next
    return result
  })
}

function ExpenseHeatmap({ analysis }: { analysis: ServiceBusinessAnalysis }) {
  const months = analysis.evolucion.map((row) => row.mes)
  const areas = [...new Set(analysis.gastos_mapa.map((row) => row.area))].sort()
  const amounts = new Map(
    analysis.gastos_mapa.map((row) => [`${row.area}|${row.mes}`, row.monto]),
  )
  const maximum = Math.max(1, ...analysis.gastos_mapa.map((row) => row.monto))

  return (
    <div className="overflow-x-auto pb-2">
      <div
        className="grid min-w-[820px] gap-1 text-[10px]"
        style={{
          gridTemplateColumns: `86px repeat(${Math.max(months.length, 1)}, minmax(50px, 1fr))`,
        }}
      >
        <div />
        {months.map((month) => (
          <div key={month} className="pb-1 text-center font-semibold text-navy/55">
            {formatMonthShort(month)}
          </div>
        ))}
        {areas.flatMap((area) => [
          <div key={`${area}-label`} className="flex items-center pr-2 font-semibold text-navy/70">
            {area}
          </div>,
          ...months.map((month) => {
            const value = amounts.get(`${area}|${month}`) ?? 0
            const ratio = value / maximum
            return (
              <div
                key={`${area}-${month}`}
                title={`${area} · ${formatMonthShort(month)}: ${formatCLP(value)}`}
                className="grid h-8 place-items-center rounded-md font-medium"
                style={{
                  backgroundColor: `rgba(26, 142, 141, ${0.08 + ratio * 0.82})`,
                  color: ratio > 0.52 ? 'white' : '#173b57',
                }}
              >
                {formatCLPCompact(value)}
              </div>
            )
          }),
        ])}
      </div>
    </div>
  )
}

export default function ServiceBusinessPanel({
  analysis,
  variant,
}: {
  analysis: ServiceBusinessAnalysis
  variant: 'summary' | 'explore'
}) {
  const { kpis, operacion } = analysis
  const cards = [
    ['Ingresos totales', kpis.ventas_netas, 'money', CircleDollarSign, 'Materiales + horas facturables + cuotas'],
    ['Costo directo', kpis.costo_directo, 'money', Wallet, 'Materiales + todas las horas + subcontratos'],
    ['Utilidad bruta', kpis.utilidad_bruta, 'money', TrendingUp, `${formatNumber(kpis.margen_bruto_pct)}% de margen`],
    ['Gastos de estructura', kpis.gastos_estructura, 'money', BriefcaseBusiness, 'Gastos fijos y variables del periodo'],
    ['Utilidad operacional', kpis.utilidad_operacional, 'money', TrendingUp, `${formatNumber(kpis.margen_operacional_pct)}% de margen`],
    ['EBITDA', kpis.ebitda, 'money', TrendingUp, `${formatNumber(kpis.margen_ebitda_pct)}% de margen`],
    ['Órdenes de trabajo', kpis.ot_total, 'number', Wrench, `${formatNumber(kpis.ot_abiertas)} abiertas`],
    ['Utilización técnica', kpis.utilizacion_pct, 'percent', Clock3, 'Horas facturables / registradas'],
    ['Horas pagadas no cobradas', kpis.costo_horas_no_facturables, 'money', ShieldAlert, 'Costo de horas no facturables'],
    ['OT con utilidad negativa', kpis.ot_perdida, 'number', ShieldAlert, `${formatNumber(kpis.ot_perdida_pct)}% del total`],
    ['Ingreso recurrente', kpis.ingreso_recurrente_pct, 'percent', BriefcaseBusiness, formatCLP(kpis.ingreso_recurrente)],
    ['Cumplimiento de SLA', kpis.cumplimiento_sla_pct, 'percent', Gauge, `${formatNumber(operacion.ot_sla_evaluadas)} OT evaluadas`],
    ['Punto de equilibrio', kpis.punto_equilibrio, 'money', Gauge, `${formatNumber(kpis.punto_equilibrio_ot)} OT equivalentes`],
    ['Backlog valorizado', kpis.backlog, 'money', Wrench, `${formatNumber(kpis.ot_abiertas)} OT abiertas`],
  ] as const

  const waterfall = waterfallRows(analysis)
  const scatterProfit = analysis.ot_dispersion.filter((row) => !row.perdida)
  const scatterLoss = analysis.ot_dispersion.filter((row) => row.perdida)
  const partialMonth = analysis.evolucion.find((row) => row.parcial)
  const clientPareto = analysis.por_cliente.slice(0, 10)
  const technicians = analysis.por_tecnico.slice(0, 16)

  return (
    <div className="space-y-5">
      <Card className="border-teal/20 bg-gradient-to-r from-teal/[0.07] via-white to-blue-50/60">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-teal">
              {variant === 'summary'
                ? 'Visión del negocio · servicios técnicos'
                : 'Exploración del negocio · servicios técnicos'}
            </p>
            <h2 className="mt-1 text-lg font-semibold text-navy">
              {variant === 'summary'
                ? 'Resultado integrado de materiales, horas y contratos'
                : 'Drivers operativos, rentabilidad y trazabilidad por relación'}
            </h2>
            <p className="mt-1 max-w-3xl text-xs leading-relaxed text-navy/60">
              Las cifras se habilitan porque las 11 fuentes y sus relaciones fueron
              validadas. Los subcontratos se tratan como costo y las tarifas se
              cruzan por técnico y vigencia.
            </p>
          </div>
          <span className="rounded-full bg-green/10 px-3 py-1 text-xs font-semibold text-green">
            100% trazable · CLP
          </span>
        </div>
      </Card>

      <div className="grid gap-2 md:grid-cols-3">
        {analysis.trazabilidad.advertencias.map((warning) => (
          <div
            key={warning}
            className={`rounded-xl border px-3 py-2.5 text-xs leading-relaxed ${
              warning.toLocaleLowerCase('es').includes('sla')
                ? 'border-coral/25 bg-coral/[0.06] text-navy/75'
                : 'border-gold/30 bg-gold/[0.07] text-navy/70'
            }`}
          >
            <span className="font-semibold">{warningLabel(warning)}</span>
            {warning}
          </div>
        ))}
      </div>

      {variant === 'summary' ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {cards.map(([label, value, format, Icon, help], index) => (
            <Card key={label} className="relative min-h-[132px] overflow-hidden">
              <span
                className="absolute inset-x-0 top-0 h-1"
                style={{ backgroundColor: CATEGORICAL[index % CATEGORICAL.length] }}
              />
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs text-navy/55">{label}</p>
                  <p className="mt-2 break-words text-xl font-semibold text-navy">
                    {value === null
                      ? 'No disponible'
                      : format === 'money'
                        ? formatCLP(value)
                        : format === 'percent'
                          ? `${formatNumber(value)}%`
                          : formatNumber(value)}
                  </p>
                  <p className="mt-1 text-[11px] leading-relaxed text-navy/45">{help}</p>
                </div>
                <span className="rounded-lg bg-work p-2">
                  <Icon className="h-4 w-4 text-teal" aria-hidden />
                </span>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-teal">Fuentes de ingreso</p>
              <p className="mt-1 text-xs leading-relaxed text-navy/60">{analysis.trazabilidad.fuentes_ingreso.join(' · ')}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-teal">Fuentes de costo</p>
              <p className="mt-1 text-xs leading-relaxed text-navy/60">{analysis.trazabilidad.fuentes_costo.join(' · ')}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-teal">Red validada</p>
              <p className="mt-1 text-xl font-semibold text-navy">{formatNumber(analysis.relaciones.length)} relaciones</p>
              <p className="text-xs text-navy/50">Claves, periodos y vigencias sin multiplicar filas</p>
            </div>
          </div>
        </Card>
      )}

      <div className="grid items-start gap-4 xl:grid-cols-2">
        <ChartCard
          title="Cascada del resultado"
          note="Puente contable acumulado: separa materiales, mano de obra, subcontratos y estructura."
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={waterfall}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="nombre" tick={{ fontSize: 9 }} interval={0} angle={-15} height={52} />
              <YAxis tickFormatter={formatCLPCompact} tick={{ fontSize: 10 }} width={60} />
              <Tooltip formatter={moneyTooltip} />
              <Bar dataKey="base" stackId="waterfall" fill="transparent" isAnimationActive={false} />
              <Bar dataKey="cambio" stackId="waterfall" radius={[4, 4, 0, 0]}>
                {waterfall.map((row) => (
                  <Cell
                    key={row.nombre}
                    fill={row.tipo === 'deduccion' ? RISK_COLOR : row.tipo === 'subtotal' ? PROFIT_COLOR : CHART.ingresos}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Ingreso mensual por fuente"
          note="Materiales, horas y contratos se apilan sin doble conteo; diciembre está marcado como parcial."
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={analysis.evolucion}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="mes" tickFormatter={formatMonthShort} tick={{ fontSize: 10 }} />
              <YAxis tickFormatter={formatCLPCompact} tick={{ fontSize: 10 }} width={60} />
              <Tooltip formatter={moneyTooltip} labelFormatter={(value) => formatMonthShort(String(value))} />
              <Legend />
              <Bar dataKey="ingreso_material" name="Materiales" stackId="income" fill={CHART.ingresos} />
              <Bar dataKey="ingreso_horas" name="Horas" stackId="income" fill={PURPLE} />
              <Bar dataKey="ingreso_contratos" name="Contratos" stackId="income" fill={PROFIT_COLOR} radius={[4, 4, 0, 0]} />
              {partialMonth && (
                <ReferenceLine
                  x={partialMonth.mes}
                  stroke={RISK_COLOR}
                  strokeDasharray="4 4"
                  label={{ value: `${partialMonth.cobertura_hasta_dia}/${partialMonth.dias_del_mes}`, fill: RISK_COLOR, fontSize: 10 }}
                />
              )}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Margen total vs margen solo OT"
          note="El margen solo OT aísla materiales y horas para no confundir mezcla contractual con mejora operativa."
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={analysis.evolucion}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="mes" tickFormatter={formatMonthShort} tick={{ fontSize: 10 }} />
              <YAxis unit="%" tick={{ fontSize: 10 }} width={44} />
              <Tooltip formatter={(value) => `${formatNumber(Number(value))}%`} />
              <Legend />
              <Line dataKey="margen_bruto_pct" name="Margen total" stroke={CHART.ingresos} strokeWidth={3} />
              <Line dataKey="margen_ot_pct" name="Margen solo OT" stroke={PURPLE} strokeWidth={2.5} />
              <ReferenceLine y={0} stroke={RISK_COLOR} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Utilización técnica mensual"
          note="Horas facturables sobre horas registradas; la línea marca la meta de 85%."
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={analysis.evolucion}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="mes" tickFormatter={formatMonthShort} tick={{ fontSize: 10 }} />
              <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 10 }} width={44} />
              <Tooltip formatter={(value) => `${formatNumber(Number(value))}%`} />
              <Bar dataKey="utilizacion_pct" name="Utilización" fill={PURPLE} radius={[4, 4, 0, 0]} />
              <ReferenceLine y={85} stroke={PROFIT_COLOR} strokeDasharray="4 4" label="meta 85%" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="OT: ingreso vs utilidad"
          note={`${formatNumber(scatterLoss.length)} OT con pérdida se destacan en coral; cada punto representa una orden real.`}
        >
          {analysis.ot_dispersion.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart>
                <CartesianGrid stroke={GRID_STROKE} />
                <XAxis type="number" dataKey="ingresos" name="Ingreso" tickFormatter={formatCLPCompact} tick={{ fontSize: 10 }} />
                <YAxis type="number" dataKey="utilidad" name="Utilidad" tickFormatter={formatCLPCompact} tick={{ fontSize: 10 }} width={60} />
                <Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={moneyTooltip} />
                <ReferenceLine y={0} stroke={RISK_COLOR} strokeWidth={2} />
                <Scatter name="OT rentables" data={scatterProfit} fill={CHART.ingresos} fillOpacity={0.45} />
                <Scatter name="OT con pérdida" data={scatterLoss} fill={RISK_COLOR} />
                <Legend />
              </ScatterChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart message="No hay órdenes con ingresos y costos suficientes para construir esta dispersión." />
          )}
        </ChartCard>

        <ChartCard
          title="Pareto de clientes por utilidad"
          note="Las barras muestran utilidad y la línea, el acumulado sobre la utilidad positiva."
        >
          {clientPareto.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={clientPareto}>
                <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                <XAxis dataKey="nombre" tick={{ fontSize: 9 }} interval={0} angle={-20} height={48} />
                <YAxis yAxisId="money" tickFormatter={formatCLPCompact} tick={{ fontSize: 10 }} width={58} />
                <YAxis yAxisId="pct" orientation="right" domain={[0, 100]} unit="%" tick={{ fontSize: 10 }} width={42} />
                <Tooltip formatter={(value, name) => name === 'Acumulado' ? `${formatNumber(Number(value))}%` : moneyTooltip(value)} />
                <Legend />
                <Bar yAxisId="money" dataKey="utilidad" name="Utilidad" fill={PROFIT_COLOR} radius={[4, 4, 0, 0]} />
                <Line yAxisId="pct" dataKey="acumulado_pct" name="Acumulado" stroke={PURPLE} strokeWidth={2.5} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart message="No hay clientes enlazados con órdenes rentables para construir el Pareto." />
          )}
        </ChartCard>

        <ChartCard
          title="Utilidad de materiales por familia"
          note="La etiqueta al final de cada barra es la utilidad por unidad, no un precio de catálogo sumado."
          className="xl:col-span-2"
          bodyClassName="h-80"
        >
          {analysis.por_familia.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={analysis.por_familia} layout="vertical" margin={{ right: 72 }}>
                <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
                <XAxis type="number" tickFormatter={formatCLPCompact} tick={{ fontSize: 10 }} />
                <YAxis type="category" dataKey="nombre" width={110} tick={{ fontSize: 10 }} />
                <Tooltip formatter={moneyTooltip} />
                <Bar dataKey="utilidad" name="Utilidad" fill={PROFIT_COLOR} radius={[0, 4, 4, 0]}>
                  <LabelList
                    dataKey="utilidad_unitaria"
                    position="right"
                    formatter={(value: unknown) => formatCLPCompact(Number(value))}
                    className="fill-navy/70 text-[10px]"
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart message="No hay líneas de materiales enlazadas con el catálogo para agrupar por familia." />
          )}
        </ChartCard>

        <ChartCard
          title="Mapa de calor de gastos"
          note="Área × mes después del unpivot. El color más intenso indica un gasto mensual mayor dentro del libro."
          className="xl:col-span-2"
          bodyClassName="h-auto min-h-72"
        >
          {analysis.gastos_mapa.length ? (
            <ExpenseHeatmap analysis={analysis} />
          ) : (
            <EmptyChart message="No hay gastos de estructura por área y periodo para construir el mapa." />
          )}
        </ChartCard>

        <ChartCard
          title="Ranking de técnicos"
          note="Ordenado por utilidad bruta por hora; la línea compara la utilización de cada técnico."
          className="xl:col-span-2"
          bodyClassName="h-[520px]"
        >
          {technicians.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={technicians} layout="vertical" margin={{ left: 18, right: 28 }}>
                <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
                <XAxis xAxisId="money" type="number" tickFormatter={formatCLPCompact} tick={{ fontSize: 10 }} />
                <XAxis xAxisId="pct" type="number" orientation="top" domain={[0, 100]} unit="%" tick={{ fontSize: 10 }} />
                <YAxis
                  type="category"
                  dataKey="nombre"
                  width={150}
                  tick={{ fontSize: 10 }}
                  tickFormatter={(value) => String(value).length > 22 ? `${String(value).slice(0, 21)}…` : String(value)}
                />
                <Tooltip formatter={(value, name) => name === 'Utilización' ? `${formatNumber(Number(value))}%` : moneyTooltip(value)} />
                <Legend />
                <Bar xAxisId="money" dataKey="utilidad_hora" name="Utilidad por hora" fill={PROFIT_COLOR} radius={[0, 4, 4, 0]} />
                <Line xAxisId="pct" dataKey="utilizacion_pct" name="Utilización" stroke={PURPLE} strokeWidth={2.5} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart message="No hay horas enlazadas con tarifas vigentes para construir el ranking técnico." />
          )}
        </ChartCard>
      </div>

      {variant === 'summary' ? (
        <Card>
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-teal">Punto de equilibrio</p>
              <p className="mt-1 text-lg font-semibold text-navy">{formatCLP(operacion.punto_equilibrio)}</p>
              <p className="text-xs text-navy/50">Apalancamiento {formatNumber(operacion.apalancamiento_operativo ?? 0)}×</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-teal">Cuotas pendientes</p>
              <p className="mt-1 text-lg font-semibold text-navy">{formatCLP(operacion.cuotas_pendientes)}</p>
              <p className="text-xs text-navy/50">{formatNumber(operacion.contratos_uf)} contratos en UF</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-coral">Riesgo operativo</p>
              <p className="mt-1 text-lg font-semibold text-navy">{formatNumber(operacion.ot_perdida)} OT con pérdida bruta</p>
              <p className="text-xs text-navy/50">{formatCLP(operacion.perdida_ot_negativas)} de pérdida acumulada</p>
            </div>
          </div>
        </Card>
      ) : (
        <Card>
          <h3 className="text-sm font-semibold text-navy">Orden sugerido de relaciones</h3>
          <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {analysis.relaciones.map((relation) => (
              <div key={relation.orden} className="rounded-lg border border-navy/10 bg-work/40 p-3">
                <p className="text-xs font-semibold text-navy">{relation.orden}. {relation.relacion}</p>
                <p className="mt-1 text-[11px] leading-relaxed text-navy/55">Desbloquea: {relation.desbloquea}</p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
