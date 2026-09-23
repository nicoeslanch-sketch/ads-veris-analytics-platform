import { useMemo, useState } from 'react'
import { ArrowRight, ChartNoAxesCombined, Lightbulb, Save, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { buildExplorationModel, explainExploration, explorationValue, explorationActions } from '../lib/explorationAnalysis'
import { CHART, GRID_STROKE, AXIS_INK, truncateLabel } from '../lib/charts'
import type { MetricsResult } from '../lib/types'
import { BusinessConclusions } from './BusinessAnalysisPanel'

export default function ExplorationAnalysis({ metrics, from, to, onSave }: {
  metrics: MetricsResult
  from?: string | null
  to?: string | null
  onSave?: (title: string, findings: string[]) => Promise<boolean>
}) {
  const [measureId, setMeasureId] = useState('')
  const [dimensionName, setDimensionName] = useState('')
  const [ranking, setRanking] = useState<'high' | 'low'>('high')
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'ok' | 'fail'>('idle')
  const model = useMemo(() => buildExplorationModel(metrics), [metrics])
  const measure = model.measures.find((item) => item.id === measureId) ?? model.measures[0]
  const dimension = measure?.dimensions.find((item) => item.name === dimensionName) ?? measure?.dimensions[0]
  const readings = measure ? explainExploration(measure, metrics.moneda, dimension?.name, from, to) : []
  const actions = measure ? explorationActions(measure, metrics, dimension?.name, from, to) : []
  const fmt = (value: number | null | undefined) => explorationValue(value, measure?.format ?? 'numero', metrics.moneda)
  const axis = (value: number) => new Intl.NumberFormat('es-CL', { notation: 'compact', maximumFractionDigits: 1 }).format(value) + (measure?.format === 'porcentaje' ? '%' : '')
  const series = measure?.series.filter((row) => (!from || row.period.slice(0, 7) >= from.slice(0, 7)) && (!to || row.period.slice(0, 7) <= to.slice(0, 7))) ?? []
  const groups = dimension?.groups.filter((row) => row.value != null && Number.isFinite(row.value)).slice().sort((a, b) => ranking === 'high' ? b.value! - a.value! : a.value! - b.value!) ?? []
  const rankRows = groups.slice(0, 6)
  const tooltipStyle = { maxWidth: 260, whiteSpace: 'normal' as const, overflowWrap: 'anywhere' as const, fontSize: 12, borderRadius: 6 }
  const save = async () => {
    if (!onSave || !measure) return
    setSaveState('saving')
    try {
      setSaveState(await onSave(measure.label + ': ' + model.subject, actions.map((item) => item.title + '. ' + item.evidence + ' ' + item.action)) ? 'ok' : 'fail')
    } catch { setSaveState('fail') }
  }

  return (
    <div className="min-w-0 space-y-6 break-words [overflow-wrap:anywhere]" data-testid="exploration-analysis">
      {metrics.analisis_negocio && !metrics.analisis_negocio.servicios
        && metrics.analisis_negocio.perfil !== 'cobranza_nominal'
        && <BusinessConclusions analysis={metrics.analisis_negocio} />}
      <section className="border-y border-navy/10 py-4" aria-labelledby="exploration-reading-title">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1 basis-56">
            <h2 id="exploration-reading-title" className="flex items-center gap-2 text-base font-semibold text-navy"><ChartNoAxesCombined className="h-5 w-5 shrink-0 text-teal" aria-hidden />Lectura del análisis</h2>
            <p className="mt-1 text-xs capitalize text-navy/60">{model.subject}</p>
          </div>
          {onSave && <button type="button" disabled={saveState === 'saving'} onClick={() => void save()} className="inline-flex max-w-full items-center gap-2 rounded-md border border-navy/20 px-3 py-2 text-xs font-medium text-navy disabled:opacity-50"><Save className="h-4 w-4 shrink-0" aria-hidden />{saveState === 'ok' ? 'Análisis guardado' : saveState === 'fail' ? 'Reintentar guardado' : saveState === 'saving' ? 'Guardando...' : 'Guardar análisis'}</button>}
        </div>
        {measure && <div className="mt-3 grid min-w-0 items-end gap-3 sm:grid-cols-2">
          <label className="min-w-0 text-xs font-semibold text-navy/65">Medida analizada
            <select value={measure.id} onChange={(event) => { setMeasureId(event.target.value); setSaveState('idle') }} className="mt-1 block w-full min-w-0 rounded-md border border-navy/20 bg-white px-3 py-2 text-sm text-navy">
              {model.measures.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </label>
          {dimension && <label className="min-w-0 text-xs font-semibold text-navy/65">Desglose analizado
            <select value={dimension.name} onChange={(event) => { setDimensionName(event.target.value); setSaveState('idle') }} className="mt-1 block w-full min-w-0 rounded-md border border-navy/20 bg-white px-3 py-2 text-sm text-navy">
              {measure.dimensions.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
            </select>
          </label>}
        </div>}
        {measure && <p className="mt-3 text-lg font-semibold text-navy">{measure.label}: {fmt(measure.value)}</p>}
      </section>

      <div className="grid min-w-0 gap-6 xl:grid-cols-2">
        {series.length > 0 && <section className="min-w-0" aria-label="Evolución analizada">
          <h3 className="text-sm font-semibold text-navy">Evolución de {measure?.label.toLowerCase()}</h3>
          <p className="mt-1 text-xs text-navy/55">{measure?.format === 'moneda' ? metrics.moneda : measure?.format === 'porcentaje' ? 'Porcentaje' : 'Unidades de la medida'} · {series[0]?.period} a {series[series.length - 1]?.period}</p>
          <div className="mt-3 h-64 min-w-0" data-testid="exploration-trend-chart">
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <LineChart data={series} margin={{ top: 12, right: 12, bottom: 0, left: 0 }} accessibilityLayer>
                <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                <XAxis dataKey="period" minTickGap={35} tick={{ fontSize: 11, fill: AXIS_INK }} tickFormatter={(value: string) => truncateLabel(value, 10)} />
                <YAxis width={56} tick={{ fontSize: 11, fill: AXIS_INK }} tickFormatter={axis} domain={['auto', 'auto']} />
                <Tooltip contentStyle={tooltipStyle} formatter={(value) => [fmt(Number(value)), measure?.label ?? 'Valor']} labelFormatter={(value) => String(value) + (series.find((row) => row.period === String(value))?.partial ? ' · cobertura parcial/no certificada' : '')} />
                <Line type="linear" dataKey="value" stroke={CHART.ingresos} strokeWidth={2} dot={{ r: 2.5 }} connectNulls={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-navy/65">{readings[0]?.evidence}</p>
        </section>}
        {rankRows.length > 0 && <section className="min-w-0" aria-label="Comparación de grupos">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-navy">{measure?.label} por {dimension?.name.toLowerCase()}</h3>
            <div role="group" aria-label="Orden del desglose" className="flex shrink-0 border-b border-navy/15">
              {(['high', 'low'] as const).map((value) => <button key={value} type="button" aria-pressed={ranking === value} onClick={() => setRanking(value)} className={'px-2 py-1.5 text-xs ' + (ranking === value ? 'border-b-2 border-teal font-semibold text-teal' : 'text-navy/60')}>{value === 'high' ? 'Mayor valor' : 'Menor valor'}</button>)}
            </div>
          </div>
          <p className="mt-1 text-xs text-navy/55">{rankRows.length} de {dimension?.totalGroups ?? groups.length} grupos disponibles · {measure?.format === 'moneda' ? metrics.moneda : measure?.label}</p>
          <div className="mt-3 h-64 min-w-0" data-testid="exploration-ranking-chart">
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <BarChart data={rankRows} layout="vertical" margin={{ top: 4, right: 10, bottom: 0, left: 0 }} accessibilityLayer>
                <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 11, fill: AXIS_INK }} tickFormatter={axis} domain={[(min: number) => Math.min(0, min), (max: number) => Math.max(0, max)]} />
                <YAxis dataKey="name" type="category" width={106} tick={{ fontSize: 11, fill: AXIS_INK }} tickFormatter={(value: string) => truncateLabel(value, 15)} interval={0} />
                <ReferenceLine x={0} stroke={AXIS_INK} />
                <Tooltip contentStyle={tooltipStyle} formatter={(value) => [fmt(Number(value)), measure?.label ?? 'Valor']} />
                <Bar dataKey="value" fill={CHART.flujo} maxBarSize={22} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-navy/65"><strong>{rankRows[0].name}</strong>: {fmt(rankRows[0].value)}. {measure?.id === 'ingresos' ? 'Ordenado por ingresos, no por unidades ni rentabilidad.' : 'El orden describe esta medida y los grupos publicados.'}</p>
        </section>}
      </div>

      <section className="border-t border-navy/10 pt-4" aria-labelledby="exploration-actions-title">
        <h2 id="exploration-actions-title" className="flex items-center gap-2 text-base font-semibold text-navy"><Lightbulb className="h-5 w-5 shrink-0 text-gold" aria-hidden />Oportunidades para revisar</h2>
        <ul className="mt-2 divide-y divide-navy/10">
          {actions.slice(0, 3).map((item) => <li key={item.title} className="min-w-0 py-3">
            <h3 className="text-sm font-semibold text-navy">{item.title}</h3>
            <p className="mt-1 text-sm leading-relaxed text-navy/70">{item.evidence}</p>
            <p className="mt-1 text-xs leading-relaxed text-teal">{item.action}</p>
          </li>)}
        </ul>
      </section>

      <details className="border-y border-navy/10 py-3" data-testid="exploration-methodology">
        <summary className="cursor-pointer text-sm font-semibold text-navy"><ShieldCheck className="mr-2 inline h-4 w-4 text-teal" aria-hidden />Calidad, conexiones y alcance · {model.cautions.length} avisos</summary>
        <p className="mt-3 text-xs leading-relaxed text-navy/65">{model.context} {measure?.formula}</p>
        <h3 className="mt-4 text-sm font-semibold text-navy">Qué limita las conclusiones</h3>
        <ul className="mt-2 list-disc space-y-2 pl-5 text-xs leading-relaxed text-navy/70">{model.cautions.map((item) => <li key={item}>{item}</li>)}</ul>
        <h3 className="mt-4 text-sm font-semibold text-navy">Qué aportan las conexiones</h3>
        <p className="mt-1 text-xs text-navy/65">La cobertura mide correspondencias por ID, no exactitud de importes ni causalidad.</p>
        {model.relations.length ? <ul className="mt-2 divide-y divide-navy/10">{model.relations.map((item) => <li key={item.name} className="py-2 text-xs text-navy/70"><strong>{item.name}</strong>: {explorationValue(item.coverage, 'porcentaje', metrics.moneda)} con correspondencia; {item.unmatched} sin correspondencia{item.missing != null ? ' y ' + item.missing + ' sin clave' : ''}.</li>)}</ul> : <p className="mt-2 text-xs text-navy/65">No hay evidencia de conexiones entre hojas en este resultado.</p>}
        <Link to="/limpieza?revision=1" className="mt-3 inline-flex items-center gap-2 text-xs font-semibold text-teal">Revisar datos de origen<ArrowRight className="h-4 w-4" aria-hidden /></Link>
      </details>

      {measure && <details className="border-b border-navy/10 pb-3">
        <summary className="cursor-pointer text-sm font-semibold text-navy">Evidencia numérica del análisis</summary>
        <div className="mt-3 grid min-w-0 gap-6 lg:grid-cols-2">
          {dimension && <div className="min-w-0"><h3 className="text-sm font-semibold text-navy">{dimension.name}</h3><dl className="mt-2 divide-y divide-navy/10">{groups.slice(0, 20).map((row, index) => <div key={row.name + '-' + index} className="grid min-w-0 grid-cols-2 gap-3 py-2 text-xs"><dt className="min-w-0 text-navy/70">{row.name}{row.records != null && <span className="block text-navy/50">{row.records.toLocaleString('es-CL')} registros</span>}</dt><dd className="min-w-0 text-right font-medium text-navy">{fmt(row.value)}</dd></div>)}</dl>{groups.length > 20 && <p className="mt-2 text-xs text-navy/50">20 de {groups.length} grupos disponibles.</p>}</div>}
          {series.length > 0 && <div className="min-w-0"><h3 className="text-sm font-semibold text-navy">Serie del período</h3><dl className="mt-2 divide-y divide-navy/10">{series.slice(-24).map((row) => <div key={row.period} className="grid min-w-0 grid-cols-2 gap-3 py-2 text-xs"><dt className="min-w-0 text-navy/70">{row.period}{row.partial && <span className="block text-navy/50">Cobertura parcial/no certificada</span>}</dt><dd className="min-w-0 text-right font-medium text-navy">{fmt(row.value)}</dd></div>)}</dl></div>}
        </div>
      </details>}
    </div>
  )
}
