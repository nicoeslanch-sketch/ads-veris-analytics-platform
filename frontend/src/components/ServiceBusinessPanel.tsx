import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
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
  Clock3,
  CircleDollarSign,
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

const COST_COLOR = '#d99018'
const PROFIT_COLOR = '#239469'
const RISK_COLOR = '#ef7657'
const PURPLE = '#8b5cf6'

function moneyTooltip(value: unknown) {
  return typeof value === 'number' ? formatCLP(value) : String(value ?? '')
}

function ChartCard({
  title,
  note,
  children,
}: {
  title: string
  note: string
  children: ReactNode
}) {
  return (
    <Card className="min-w-0">
      <h3 className="text-sm font-semibold text-navy">{title}</h3>
      <p className="mt-1 text-xs text-navy/55">{note}</p>
      <div className="mt-4 h-72 min-w-0">{children}</div>
    </Card>
  )
}

export default function ServiceBusinessPanel({
  analysis,
}: {
  analysis: ServiceBusinessAnalysis
}) {
  const { kpis, operacion } = analysis
  const cards = [
    ['Ventas netas', kpis.ventas_netas, 'money', CircleDollarSign, 'Materiales + horas facturables + cuotas'],
    ['Costo directo', kpis.costo_directo, 'money', Wallet, 'Materiales + todas las horas + subcontratos'],
    ['Utilidad bruta', kpis.utilidad_bruta, 'money', TrendingUp, 'Antes de gastos de estructura'],
    ['Margen bruto', kpis.margen_bruto_pct, 'percent', Gauge, 'Utilidad bruta / ventas'],
    ['Gastos de estructura', kpis.gastos_estructura, 'money', BriefcaseBusiness, 'Fijos y variables del periodo'],
    ['Utilidad operacional', kpis.utilidad_operacional, 'money', TrendingUp, 'Después de estructura'],
    ['Margen operacional', kpis.margen_operacional_pct, 'percent', Gauge, 'Resultado operacional / ventas'],
    ['EBITDA', kpis.ebitda, 'money', TrendingUp, 'Resultado operacional + depreciación'],
    ['Margen EBITDA', kpis.margen_ebitda_pct, 'percent', Gauge, 'EBITDA / ventas'],
    ['Utilización técnica', kpis.utilizacion_pct, 'percent', Clock3, 'Horas facturables / registradas'],
    ['Horas no facturables', kpis.costo_horas_no_facturables, 'money', ShieldAlert, 'Costo pagado que no se cobró'],
    ['Backlog valorizado', kpis.backlog, 'money', Wrench, `${formatNumber(operacion.ot_abiertas)} OT abiertas`],
    ['OT con pérdida bruta', kpis.ot_perdida, 'number', ShieldAlert, `${formatNumber(operacion.ot_perdida_operacional)} con pérdida operacional`],
    ['Ingreso recurrente', kpis.ingreso_recurrente, 'money', BriefcaseBusiness, `${formatNumber(operacion.contratos)} contratos`],
  ] as const

  const waterfall = analysis.cascada.map((row) => ({
    ...row,
    positivo: row.valor >= 0 ? row.valor : 0,
    negativo: row.valor < 0 ? row.valor : 0,
  }))
  const scatterProfit = analysis.ot_dispersion.filter((row) => !row.perdida)
  const scatterLoss = analysis.ot_dispersion.filter((row) => row.perdida)

  return (
    <div className="space-y-5">
      <Card className="border-teal/20 bg-gradient-to-r from-teal/[0.07] via-white to-blue-50/60">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-teal">
              Visión del negocio · servicios técnicos
            </p>
            <h2 className="mt-1 text-lg font-semibold text-navy">
              Resultado integrado de materiales, horas y contratos
            </h2>
            <p className="mt-1 max-w-3xl text-xs leading-relaxed text-navy/60">
              Las cifras se habilitan porque las 11 fuentes y sus relaciones fueron validadas.
              Los subcontratos se tratan como costo y las tarifas se cruzan por vigencia.
            </p>
          </div>
          <span className="rounded-full bg-green/10 px-3 py-1 text-xs font-semibold text-green">
            100% trazable · CLP
          </span>
        </div>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {cards.map(([label, value, format, Icon, help], index) => (
          <Card key={label} className="relative overflow-hidden">
            <span
              className="absolute inset-x-0 top-0 h-1"
              style={{ backgroundColor: CATEGORICAL[index % CATEGORICAL.length] }}
            />
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs text-navy/55">{label}</p>
                <p className="mt-2 break-words text-xl font-semibold text-navy">
                  {format === 'money'
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

      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard
          title="Ventas, costo directo y utilidad por mes"
          note="Diciembre parcial se marca y no debe interpretarse como una caída comparable."
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={analysis.evolucion}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="mes" tickFormatter={formatMonthShort} tick={{ fontSize: 10 }} />
              <YAxis tickFormatter={formatCLPCompact} tick={{ fontSize: 10 }} width={58} />
              <Tooltip
                formatter={moneyTooltip}
                labelFormatter={(value) => formatMonthShort(String(value))}
              />
              <Legend />
              <Bar dataKey="ingresos" name="Ventas" fill={CHART.ingresos} radius={[4, 4, 0, 0]} />
              <Line dataKey="costo_directo" name="Costo directo" stroke={COST_COLOR} strokeWidth={2} dot={false} />
              <Line dataKey="utilidad_bruta" name="Utilidad bruta" stroke={PROFIT_COLOR} strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Evolución de márgenes"
          note="Distingue el margen del trabajo antes y después de la estructura."
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={analysis.evolucion}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="mes" tickFormatter={formatMonthShort} tick={{ fontSize: 10 }} />
              <YAxis unit="%" tick={{ fontSize: 10 }} width={42} />
              <Tooltip formatter={(value) => `${formatNumber(Number(value))}%`} />
              <Legend />
              <Line dataKey="margen_bruto_pct" name="Margen bruto" stroke={CHART.ingresos} strokeWidth={3} />
              <Line dataKey="margen_operacional_pct" name="Margen operacional" stroke={PURPLE} strokeWidth={2} />
              <ReferenceLine y={0} stroke={RISK_COLOR} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Cascada del resultado"
          note="Puente desde ingresos hasta utilidad operacional y EBITDA."
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={waterfall}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="nombre" tick={{ fontSize: 9 }} interval={0} angle={-15} height={48} />
              <YAxis tickFormatter={formatCLPCompact} tick={{ fontSize: 10 }} width={58} />
              <Tooltip formatter={moneyTooltip} />
              <ReferenceLine y={0} stroke="#9aa7b5" />
              <Bar dataKey="positivo" name="Aporte" fill={PROFIT_COLOR} radius={[4, 4, 0, 0]} />
              <Bar dataKey="negativo" name="Deducción" fill={RISK_COLOR} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Órdenes de trabajo: ingreso vs utilidad"
          note={`${formatNumber(scatterLoss.length)} OT bajo cero aparecen en coral; cada punto es una OT real.`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart>
              <CartesianGrid stroke={GRID_STROKE} />
              <XAxis type="number" dataKey="ingresos" name="Ingreso" tickFormatter={formatCLPCompact} tick={{ fontSize: 10 }} />
              <YAxis type="number" dataKey="utilidad" name="Utilidad" tickFormatter={formatCLPCompact} tick={{ fontSize: 10 }} width={58} />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={moneyTooltip} />
              <ReferenceLine y={0} stroke={RISK_COLOR} strokeWidth={2} />
              <Scatter name="OT rentables" data={scatterProfit} fill={CHART.ingresos} fillOpacity={0.55} />
              <Scatter name="OT con pérdida" data={scatterLoss} fill={RISK_COLOR} />
              <Legend />
            </ScatterChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Composición de ingresos" note="El ingreso no vive en una sola hoja: se integra sin doble conteo.">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={analysis.composicion_ingresos} dataKey="valor" nameKey="nombre" innerRadius={58} outerRadius={98} paddingAngle={2}>
                {analysis.composicion_ingresos.map((row, index) => (
                  <Cell key={row.nombre} fill={CATEGORICAL[index % CATEGORICAL.length]} />
                ))}
              </Pie>
              <Tooltip formatter={moneyTooltip} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Composición de costos y estructura" note="Separa los recursos directos del costo fijo y variable de sostener la operación.">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={analysis.composicion_costos} dataKey="valor" nameKey="nombre" innerRadius={52} outerRadius={98}>
                {analysis.composicion_costos.map((row, index) => (
                  <Cell key={row.nombre} fill={CATEGORICAL[(index + 1) % CATEGORICAL.length]} />
                ))}
              </Pie>
              <Tooltip formatter={moneyTooltip} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Utilización técnica mensual" note="Horas facturables sobre horas registradas; el KPI principal del negocio de servicios.">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={analysis.evolucion}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="mes" tickFormatter={formatMonthShort} tick={{ fontSize: 10 }} />
              <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 10 }} width={42} />
              <Tooltip formatter={(value) => `${formatNumber(Number(value))}%`} />
              <Bar dataKey="utilizacion_pct" name="Utilización" fill={PURPLE} radius={[4, 4, 0, 0]} />
              <ReferenceLine y={85} stroke={PROFIT_COLOR} strokeDasharray="4 4" label="meta 85%" />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Rentabilidad por tipo de OT" note="Compara ingreso y utilidad sin presentar una tabla extensa.">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={analysis.por_tipo_ot} layout="vertical">
              <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
              <XAxis type="number" tickFormatter={formatCLPCompact} tick={{ fontSize: 10 }} />
              <YAxis type="category" dataKey="nombre" width={86} tick={{ fontSize: 10 }} />
              <Tooltip formatter={moneyTooltip} />
              <Legend />
              <Bar dataKey="ingresos" name="Ingreso" fill={CHART.ingresos} radius={[0, 4, 4, 0]} />
              <Bar dataKey="utilidad" name="Utilidad" fill={PROFIT_COLOR} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Rentabilidad de materiales por familia" note="Ingreso, costo y utilidad por familia; no confunde costo unitario con gasto total.">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={analysis.por_familia}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="nombre" tick={{ fontSize: 9 }} interval={0} angle={-15} height={48} />
              <YAxis tickFormatter={formatCLPCompact} tick={{ fontSize: 10 }} width={58} />
              <Tooltip formatter={moneyTooltip} />
              <Legend />
              <Bar dataKey="ingresos" name="Ingreso" fill={CHART.ingresos} />
              <Bar dataKey="costo" name="Costo" fill={COST_COLOR} />
              <Bar dataKey="utilidad" name="Utilidad" fill={PROFIT_COLOR} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

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
    </div>
  )
}
