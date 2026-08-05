import {
  Bar,
  BarChart,
  ComposedChart,
  CartesianGrid,
  Cell,
  Legend,
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
  const tooltipFormatter = (value: unknown, name?: string | number): [string, string] => {
    const displayName = String(name ?? primary?.label ?? '')
    const series = chart.series.find((item) => item.label === displayName) ?? primary
    const valueFormat = series?.format ?? format
    return [
    value === null || value === undefined
      ? 'No disponible'
      : formatKpiValue(Number(value), valueFormat, currency),
    displayName,
    ]
  }
  const seriesColor = (series: RelationshipChart['series'][number], index: number) => {
    if (series.color_role === 'cost') return CHART.gastos
    if (series.color_role === 'profit') return CHART.utilidad
    if (series.color_role === 'warning') return CHART.gastos
    if (series.color_role === 'risk') return CHART.alerta
    return CATEGORICAL[index % CATEGORICAL.length]
  }

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
          {chart.kind === 'donut' && chart.data.length >= 3 ? (
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
              {chart.series.map((series, index) => (
                <Line
                  key={series.key}
                  type="monotone"
                  dataKey={series.key}
                  name={series.label}
                  stroke={seriesColor(series, index)}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          ) : chart.kind === 'combo' ? (
            <ComposedChart data={chart.data} margin={{ top: 8, right: 8, bottom: 8, left: 4 }}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis
                dataKey={chart.category_key}
                tick={{ fill: AXIS_INK, fontSize: 10 }}
                tickFormatter={(value: string) => truncateLabel(String(value), 11)}
              />
              <YAxis
                yAxisId="left"
                tick={{ fill: AXIS_INK, fontSize: 10 }}
                tickFormatter={axisFormatter(
                  chart.series.find((series) => series.axis !== 'right')?.format ?? format,
                  currency,
                )}
                width={58}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fill: AXIS_INK, fontSize: 10 }}
                tickFormatter={axisFormatter(
                  chart.series.find((series) => series.axis === 'right')?.format ?? 'percent',
                  currency,
                )}
                width={42}
              />
              <Tooltip formatter={tooltipFormatter} />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              {chart.series.map((series, index) => (
                series.kind === 'line' ? (
                  <Line
                    key={series.key}
                    yAxisId={series.axis ?? 'left'}
                    type="monotone"
                    dataKey={series.key}
                    name={series.label}
                    stroke={seriesColor(series, index)}
                    strokeWidth={2.5}
                    dot={{ r: 3 }}
                  />
                ) : (
                  <Bar
                    key={series.key}
                    yAxisId={series.axis ?? 'left'}
                    dataKey={series.key}
                    name={series.label}
                    fill={seriesColor(series, index)}
                    stackId={chart.stacked ? 'total' : undefined}
                    radius={[3, 3, 0, 0]}
                  />
                )
              ))}
            </ComposedChart>
          ) : chart.orientation === 'horizontal' ? (
            <BarChart
              data={chart.data}
              layout="vertical"
              margin={{ top: 4, right: 18, bottom: 4, left: 8 }}
            >
              <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
              <XAxis type="number" tick={{ fill: AXIS_INK, fontSize: 10 }} tickFormatter={tickFormat} />
              <YAxis
                type="category"
                dataKey={chart.category_key}
                tick={{ fill: AXIS_INK, fontSize: 10 }}
                tickFormatter={(value: string) => truncateLabel(String(value), 18)}
                width={116}
              />
              <Tooltip formatter={tooltipFormatter} cursor={{ fill: '#00a8a814' }} />
              {chart.series.map((series, index) => (
                <Bar
                  key={series.key}
                  dataKey={series.key}
                  name={series.label}
                  fill={seriesColor(series, index)}
                  radius={[0, 4, 4, 0]}
                  maxBarSize={22}
                />
              ))}
            </BarChart>
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
              {chart.series.map((series, index) => (
                <Bar
                  key={series.key}
                  dataKey={series.key}
                  name={series.label}
                  fill={seriesColor(series, index)}
                  stackId={chart.stacked ? 'total' : undefined}
                  radius={[4, 4, 0, 0]}
                />
              ))}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
      {chart.note && (
        <p className="mt-2 text-[10px] leading-relaxed text-navy/45">{chart.note}</p>
      )}
    </Card>
  )
}

/** Renderiza los gráficos del contrato. Si no hay datos válidos no muestra nada
 * (el backend ya omite los gráficos sin información). */
export default function RelationshipCharts({ charts, currency }: RelationshipChartsProps) {
  const usable = charts.filter((chart) => chart.data.length > 0)
  if (!usable.length) return null
  return (
    <div className={`@container grid gap-3 ${usable.length > 1 ? '@min-[680px]:grid-cols-2' : ''}`}>
      {usable.map((chart) => (
        <ChartFrame key={chart.id} chart={chart} currency={currency} />
      ))}
    </div>
  )
}
