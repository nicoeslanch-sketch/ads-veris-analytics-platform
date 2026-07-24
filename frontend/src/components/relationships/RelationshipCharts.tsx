import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { HelpCircle } from 'lucide-react'
import Card from '../ui/Card'
import { AXIS_INK, CATEGORICAL, CHART, GRID_STROKE, formatCLPCompact, truncateLabel } from '../../lib/charts'
import { formatKpiValue } from '../../lib/relationshipDashboard'
import type { KpiFormat, RelationshipChart } from '../../lib/types'

interface RelationshipChartsProps {
  charts: RelationshipChart[]
  currency: string
}

function axisFormatter(format: KpiFormat, currency: string) {
  return (value: number) => {
    if (format === 'currency') return formatCLPCompact(value).replace('$', currency === 'USD' ? 'US$' : '$')
    if (format === 'percent') return `${Math.round(value)}%`
    if (format === 'days') return `${Math.round(value)}d`
    return String(Math.round(value))
  }
}

function ChartFrame({ chart, currency }: { chart: RelationshipChart; currency: string }) {
  const primary = chart.series[0]
  const format = primary?.format ?? 'number'
  const tickFormat = axisFormatter(format, currency)
  const tooltipFormatter = (value: unknown): [string, string] => [
    value === null || value === undefined
      ? 'No disponible'
      : formatKpiValue(Number(value), format, currency),
    primary?.label ?? '',
  ]

  return (
    <Card className="!p-4">
      <div className="mb-3 flex items-center gap-1.5">
        <h4 className="text-sm font-semibold text-navy">{chart.title}</h4>
        {chart.help && (
          <span title={chart.help} className="text-navy/30">
            <HelpCircle className="h-3.5 w-3.5" aria-hidden />
            <span className="sr-only">{chart.help}</span>
          </span>
        )}
      </div>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {chart.kind === 'donut' ? (
            <PieChart>
              <Pie
                data={chart.data}
                dataKey={primary?.key ?? 'value'}
                nameKey={chart.category_key}
                innerRadius="55%"
                outerRadius="85%"
                paddingAngle={2}
              >
                {chart.data.map((_, index) => (
                  <Cell key={index} fill={CATEGORICAL[index % CATEGORICAL.length]} />
                ))}
              </Pie>
              <Tooltip formatter={tooltipFormatter} />
            </PieChart>
          ) : chart.kind === 'line' ? (
            <LineChart data={chart.data} margin={{ top: 8, right: 12, bottom: 8, left: 4 }}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis
                dataKey={chart.category_key}
                tick={{ fill: AXIS_INK, fontSize: 11 }}
                tickFormatter={(value: string) => truncateLabel(String(value), 12)}
              />
              <YAxis tick={{ fill: AXIS_INK, fontSize: 11 }} tickFormatter={tickFormat} width={54} />
              <Tooltip formatter={tooltipFormatter} />
              <Line type="monotone" dataKey={primary?.key ?? 'value'} stroke={CHART.ingresos} strokeWidth={2} dot={false} />
            </LineChart>
          ) : (
            <BarChart data={chart.data} margin={{ top: 8, right: 12, bottom: 8, left: 4 }}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis
                dataKey={chart.category_key}
                tick={{ fill: AXIS_INK, fontSize: 11 }}
                interval={0}
                angle={-20}
                textAnchor="end"
                height={54}
                tickFormatter={(value: string) => truncateLabel(String(value), 12)}
              />
              <YAxis tick={{ fill: AXIS_INK, fontSize: 11 }} tickFormatter={tickFormat} width={54} />
              <Tooltip formatter={tooltipFormatter} cursor={{ fill: '#00a8a814' }} />
              <Bar dataKey={primary?.key ?? 'value'} radius={[4, 4, 0, 0]}>
                {chart.data.map((_, index) => (
                  <Cell key={index} fill={CATEGORICAL[index % CATEGORICAL.length]} />
                ))}
              </Bar>
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

/** Renderiza los gráficos del contrato. Si no hay datos válidos no muestra nada
 * (el backend ya omite los gráficos sin información). */
export default function RelationshipCharts({ charts, currency }: RelationshipChartsProps) {
  const usable = charts.filter((chart) => chart.data.length > 0)
  if (!usable.length) return null
  return (
    <div className={`grid gap-4 ${usable.length > 1 ? 'lg:grid-cols-2' : ''}`}>
      {usable.map((chart) => (
        <ChartFrame key={chart.id} chart={chart} currency={currency} />
      ))}
    </div>
  )
}
