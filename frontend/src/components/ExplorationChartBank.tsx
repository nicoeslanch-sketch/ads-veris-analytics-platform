import { useMemo, useState } from 'react'
import { ChartNoAxesCombined, Lightbulb } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { buildExplorationViews, type ExplorationView } from '../lib/explorationViews'
import { AXIS_INK, CHART, GRID_STROKE, truncateLabel } from '../lib/charts'
import { explorationValue } from '../lib/explorationAnalysis'

type Props = Parameters<typeof buildExplorationViews>[0]
const colors = [CHART.ingresos, '#b45309', '#be185d', '#2563eb', '#64748b']
const tip = { maxWidth: 270, whiteSpace: 'normal' as const, overflowWrap: 'anywhere' as const, fontSize: 12 }

function viewValue(view: ExplorationView, value: unknown, currency: string) {
  const points = view.id === 'monthly-change' && view.unit === 'percent'
  return explorationValue(typeof value === 'number' ? value : null, view.unit === 'money' ? 'moneda' : view.unit === 'percent' && !points ? 'porcentaje' : 'numero', currency) + (points && typeof value === 'number' ? ' pp' : '')
}

function EvidenceChart({ view, currency }: { view: ExplorationView; currency: string }) {
  const points = view.id === 'monthly-change' && view.unit === 'percent'
  const format = (value: unknown) => viewValue(view, value, currency)
  const compact = (value: number) => new Intl.NumberFormat('es-CL', { notation: 'compact', maximumFractionDigits: 1 }).format(value) + (points ? ' pp' : view.unit === 'percent' ? '%' : '')
  if (view.kind === 'matrix') {
    const max = Math.max(1, ...view.rows.flatMap(row => view.keys.map(key => typeof row[key.key] === 'number' ? Math.abs(Number(row[key.key])) : 0)))
    return <div className="mt-3 max-w-full overflow-x-auto" tabIndex={0} role="region" aria-label={view.label}>
      <table className="w-full border-collapse text-xs"><thead><tr><th className="min-w-36 p-2 text-left">Grupo</th>{view.keys.map(key => <th key={key.key} className="min-w-24 p-2 font-medium">{key.label}</th>)}</tr></thead>
        <tbody>{view.rows.map((row, i) => <tr key={i}><th className="max-w-52 break-words p-2 text-left font-medium [overflow-wrap:anywhere]">{row.name}</th>{view.keys.map(key => {
          const value = row[key.key]
          const numeric = typeof value === 'number' ? value : null
          return <td key={key.key} className="border border-white p-2 text-right tabular-nums" title={`${row.name} · ${key.label}: ${format(value)}`} style={{ backgroundColor: numeric == null ? '#f3f4f6' : `rgba(${numeric < 0 ? '190,24,93' : '13,148,136'},${.05 + .3 * Math.abs(numeric) / max})` }}>{numeric == null ? 'Sin dato' : compact(numeric)}</td>
        })}</tr>)}</tbody></table>
    </div>
  }
  if (view.kind === 'scatter') return <div className="mt-3 h-80 min-w-0"><ResponsiveContainer width="100%" height="100%" minWidth={0}>
    <ScatterChart margin={{ top: 12, right: 15, bottom: 24, left: 5 }} accessibilityLayer>
      <CartesianGrid stroke={GRID_STROKE} /><XAxis type="number" dataKey="x" name="Ingresos netos" padding={{ left: 8, right: 8 }} tickFormatter={compact} tick={{ fontSize: 10 }} label={{ value: 'Ingresos netos', position: 'bottom', fontSize: 11 }} />
      <YAxis type="number" dataKey="y" name="Utilidad bruta" padding={{ top: 12, bottom: 8 }} width={64} tickFormatter={compact} tick={{ fontSize: 10 }} />
      <ReferenceLine y={0} stroke={AXIS_INK} /><ReferenceLine x={0} stroke={AXIS_INK} />
      <Tooltip content={({ active, payload }) => active && payload?.[0] ? <div className="rounded-md border border-navy/15 bg-white p-3 shadow-sm" style={tip}><strong>{payload[0].payload.name}</strong><p>Ingresos: {format(payload[0].payload.x)}</p><p>Utilidad bruta: {format(payload[0].payload.y)}</p></div> : null} />
      <Scatter data={view.rows} fill={CHART.ingresos} isAnimationActive={false} />
    </ScatterChart></ResponsiveContainer></div>
  if (view.kind === 'comparison' || view.kind === 'pareto' || view.kind === 'line') return <div className="mt-3 h-80 min-w-0"><ResponsiveContainer width="100%" height="100%" minWidth={0}>
    <ComposedChart data={view.rows} margin={{ top: 12, right: 5, bottom: 0, left: 0 }} accessibilityLayer>
      <CartesianGrid stroke={GRID_STROKE} vertical={false} /><XAxis dataKey="name" minTickGap={24} tick={{ fontSize: 10 }} tickFormatter={v => truncateLabel(String(v), 12)} />
      <YAxis yAxisId="value" width={60} tickFormatter={compact} tick={{ fontSize: 10 }} />
      {view.kind === 'pareto' && <YAxis yAxisId="share" orientation="right" width={40} domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} />}
      <Tooltip contentStyle={tip} formatter={(value, name) => [name === 'Acumulado' ? `${Number(value).toFixed(1)}%` : format(value), name]} />
      <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
      {view.keys.map((key, i) => view.kind === 'pareto' ? <Bar key={key.key} yAxisId="value" dataKey={key.key} name={key.label} fill={colors[i % colors.length]} maxBarSize={34} isAnimationActive={false} /> : <Line key={key.key} yAxisId="value" dataKey={key.key} name={key.label} stroke={colors[i % colors.length]} type="linear" connectNulls={false} dot={{ r: 3 }} strokeWidth={2} isAnimationActive={false} />)}
      {view.kind === 'pareto' && <Line yAxisId="share" dataKey="cumulative" name="Acumulado" stroke="#b45309" dot={false} strokeWidth={2} isAnimationActive={false} />}
    </ComposedChart></ResponsiveContainer></div>
  return <div className="mt-3 min-w-0" style={{ height: Math.max(220, Math.min(560, view.rows.length * 30 + 45)) }}><ResponsiveContainer width="100%" height="100%" minWidth={0}>
    <BarChart data={view.rows} layout="vertical" margin={{ top: 8, right: 10, bottom: 0, left: 0 }} accessibilityLayer>
      <CartesianGrid stroke={GRID_STROKE} horizontal={false} /><XAxis type="number" tickFormatter={compact} tick={{ fontSize: 10 }} domain={view.id.startsWith('recurring-peak') ? [0, 100] : [(n: number) => Math.min(0, n), (n: number) => Math.max(0, n)]} />
      <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 10 }} tickFormatter={v => truncateLabel(String(v), 16)} interval={0} />
      <ReferenceLine x={0} stroke={AXIS_INK} /><Tooltip contentStyle={tip} formatter={(value) => [format(value), view.keys[0].label]} />
      <Bar dataKey="value" fill={CHART.ingresos} maxBarSize={22} isAnimationActive={false} />
    </BarChart></ResponsiveContainer></div>
}

export default function ExplorationChartBank(props: Props) {
  const views = useMemo(() => buildExplorationViews(props), [props.metrics, props.ledger, props.measure, props.dimension, props.from, props.to])
  const [selection, setSelection] = useState('')
  const selected = views.find(view => view.id === selection) ?? views.find(view => view.id === 'recurring-peak') ?? views[0]
  const currency = props.ledger?.moneda ?? props.metrics?.moneda ?? 'CLP'
  if (!selected) return null
  return <section className="min-w-0 border-y border-navy/10 py-4" data-testid="exploration-chart-bank">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <h2 className="flex items-center gap-2 text-base font-semibold text-navy"><ChartNoAxesCombined className="h-5 w-5 shrink-0 text-teal" />Profundizar en los datos</h2>
      <label className="min-w-0 w-full text-xs text-navy/65 sm:w-80">Pregunta de análisis
        <select value={selected.id} onChange={event => setSelection(event.target.value)} className="mt-1 block w-full min-w-0 rounded-md border border-navy/20 bg-white p-2 text-sm text-navy">
          {(['Evolución', 'Composición', 'Productos', 'Operación'] as const).map(category => views.some(view => view.category === category) && <optgroup key={category} label={category}>{views.filter(view => view.category === category).map(view => <option key={view.id} value={view.id}>{view.label}</option>)}</optgroup>)}
        </select>
      </label>
    </div>
    <h3 className="mt-4 text-sm font-semibold text-navy">{selected.label}</h3>
    <p className="mt-1 text-xs text-navy/65">{selected.unit === 'money' ? currency : selected.unit === 'percent' ? selected.id === 'monthly-change' ? 'Puntos porcentuales' : 'Porcentaje' : 'Conteo'}{selected.kind === 'scatter' ? ' · Eje vertical: utilidad bruta' : ''}</p>
    <EvidenceChart view={selected} currency={currency} />
    <p className="mt-3 text-xs leading-relaxed text-navy/70">{selected.evidence}</p>
    <p className="mt-2 text-sm leading-relaxed text-[#08756e]"><Lightbulb className="mr-1 inline h-4 w-4" aria-hidden />{selected.action}</p>
    <details className="mt-3 text-xs text-navy/65"><summary className="cursor-pointer font-medium">Ver valores exactos</summary>
      <div className="mt-2 max-h-72 overflow-auto" tabIndex={0} role="region" aria-label="Valores del gráfico"><table className="w-full text-left"><thead><tr><th className="p-2">Grupo / período</th>{selected.keys.map(key => <th key={key.key} className="p-2">{key.label}</th>)}</tr></thead><tbody>{selected.rows.map((row, i) => <tr key={i} className="border-t border-navy/10"><th className="max-w-52 break-words p-2 font-normal [overflow-wrap:anywhere]">{row.name}</th>{selected.keys.map(key => <td key={key.key} className="whitespace-nowrap p-2 tabular-nums">{viewValue(selected, row[key.key], currency)}</td>)}</tr>)}</tbody></table></div>
    </details>
  </section>
}
