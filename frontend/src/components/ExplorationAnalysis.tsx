import { useMemo, useState } from 'react'
import { ArrowRight, BookOpen, GitMerge, Save, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { buildExplorationModel, explainExploration, explorationValue } from '../lib/explorationAnalysis'
import type { MetricsResult } from '../lib/types'

export default function ExplorationAnalysis({ metrics, from, to, onSave }: {
  metrics: MetricsResult
  from?: string | null
  to?: string | null
  onSave?: (title: string, findings: string[]) => Promise<boolean>
}) {
  const [measureId, setMeasureId] = useState('')
  const [dimensionName, setDimensionName] = useState('')
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'ok' | 'fail'>('idle')
  const model = useMemo(() => buildExplorationModel(metrics), [metrics])
  const measure = model.measures.find((item) => item.id === measureId) ?? model.measures[0]
  const dimension = measure?.dimensions.find((item) => item.name === dimensionName) ?? measure?.dimensions[0]
  const readings = measure ? explainExploration(measure, metrics.moneda, dimension?.name, from, to) : []
  const fmt = (value: number | null | undefined) => explorationValue(value, measure?.format ?? 'numero', metrics.moneda)
  const save = async () => {
    if (!onSave || !measure) return
    setSaveState('saving')
    try {
      setSaveState(await onSave(`${measure.label}: ${model.subject}`, readings.map((item) => `${item.title}. ${item.evidence} ${item.meaning}`)) ? 'ok' : 'fail')
    } catch {
      setSaveState('fail')
    }
  }

  return (
    <div className="min-w-0 space-y-7 break-words [overflow-wrap:anywhere]" data-testid="exploration-analysis">
      <section className="border-y border-navy/10 py-5" aria-labelledby="exploration-reading-title">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1 basis-72">
            <h2 id="exploration-reading-title" className="flex items-center gap-2 text-lg font-semibold text-navy"><BookOpen className="h-5 w-5 shrink-0 text-teal" aria-hidden />Lectura del análisis</h2>
            <p className="mt-2 text-sm font-semibold capitalize text-navy">{model.subject}</p>
            <p className="mt-1 max-w-4xl text-sm leading-relaxed text-navy/70">{model.context}</p>
          </div>
          {onSave && <button type="button" disabled={saveState === 'saving'} onClick={() => void save()} className="inline-flex max-w-full items-center justify-center gap-2 rounded-lg border border-navy/20 bg-white px-3 py-2 text-sm font-medium text-navy disabled:opacity-50"><Save className="h-4 w-4 shrink-0" aria-hidden />{saveState === 'ok' ? 'Análisis guardado' : saveState === 'fail' ? 'Reintentar guardado' : saveState === 'saving' ? 'Guardando...' : 'Guardar análisis'}</button>}
        </div>
        {measure && <>
          <div className="mt-5 grid min-w-0 gap-3 sm:grid-cols-2">
            <label className="min-w-0 text-xs font-semibold text-navy/65">Medida analizada
              <select value={measure.id} onChange={(event) => { setMeasureId(event.target.value); setSaveState('idle') }} className="mt-1 block w-full min-w-0 max-w-full rounded-lg border border-navy/20 bg-white px-3 py-2 text-sm font-medium text-navy">
                {model.measures.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
            </label>
            {measure.dimensions.length > 0 && <label className="min-w-0 text-xs font-semibold text-navy/65">Desglose analizado
              <select value={dimension?.name ?? ''} onChange={(event) => { setDimensionName(event.target.value); setSaveState('idle') }} className="mt-1 block w-full min-w-0 max-w-full rounded-lg border border-navy/20 bg-white px-3 py-2 text-sm font-medium text-navy">
                {measure.dimensions.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
              </select>
            </label>}
          </div>
          <p className="mt-4 text-base leading-relaxed text-navy"><strong>{measure.label}: {fmt(measure.value)}.</strong></p>
          <p className="mt-1 text-xs leading-relaxed text-navy/60">{measure.formula}</p>
        </>}
      </section>

      <section aria-labelledby="exploration-findings-title">
        <h2 id="exploration-findings-title" className="text-base font-semibold text-navy">Qué muestran las diferencias</h2>
        <div className="mt-3 divide-y divide-navy/10">
          {readings.map((reading) => <article key={reading.title} className="grid min-w-0 gap-3 py-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-8">
            <div className="min-w-0"><h3 className="text-sm font-semibold text-navy">{reading.title}</h3><p className="mt-2 text-sm leading-relaxed text-navy/75">{reading.evidence}</p></div>
            <div className="min-w-0"><p className="text-sm leading-relaxed text-navy/75">{reading.meaning}</p><p className="mt-2 text-xs leading-relaxed text-teal"><strong>Para comprobarlo: </strong>{reading.next}</p></div>
          </article>)}
        </div>
      </section>

      <section className="border-t border-navy/10 pt-5" aria-labelledby="exploration-confidence-title">
        <h2 id="exploration-confidence-title" className="flex items-center gap-2 text-base font-semibold text-navy"><ShieldCheck className="h-5 w-5 shrink-0 text-teal" aria-hidden />Qué limita las conclusiones</h2>
        <ul className="mt-3 grid gap-x-8 gap-y-3 lg:grid-cols-2">
          {model.cautions.map((caution) => <li key={caution} className="min-w-0 border-l-2 border-gold/60 pl-3 text-sm leading-relaxed text-navy/75">{caution}</li>)}
        </ul>
        <Link to="/limpieza?revision=1" className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-teal">Revisar datos de origen<ArrowRight className="h-4 w-4 shrink-0" aria-hidden /></Link>
      </section>

      <section className="border-t border-navy/10 pt-5" aria-labelledby="exploration-relations-title">
        <h2 id="exploration-relations-title" className="flex items-center gap-2 text-base font-semibold text-navy"><GitMerge className="h-5 w-5 shrink-0 text-teal" aria-hidden />Qué aportan las conexiones</h2>
        {model.relations.length ? <>
          <p className="mt-2 text-sm leading-relaxed text-navy/70">La coincidencia de IDs permite incorporar atributos de otra hoja. La cobertura mide correspondencias, no demuestra una relación causal ni certifica los importes.</p>
          <ul className="mt-3 divide-y divide-navy/10">
            {model.relations.map((relation) => <li key={relation.name} className="grid min-w-0 gap-1 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] sm:gap-4"><strong className="min-w-0 text-sm text-navy">{relation.name}</strong><p className="min-w-0 text-sm text-navy/70">{relation.matched.toLocaleString('es-CL')} de {relation.rows.toLocaleString('es-CL')} registros con correspondencia ({explorationValue(relation.coverage, 'porcentaje', metrics.moneda)}). {relation.unmatched.toLocaleString('es-CL')} sin correspondencia{relation.missing != null ? ` y ${relation.missing.toLocaleString('es-CL')} sin clave` : ' (sin desglose de claves ausentes)'}.</p></li>)}
          </ul>
        </> : <p className="mt-2 text-sm leading-relaxed text-navy/70">Este resultado no incluye evidencia de correspondencias entre hojas. No se atribuyen costos, pagos ni atributos de otra tabla solo porque sus nombres se parezcan.</p>}
      </section>

      <section className="border-t border-navy/10 pt-5" aria-labelledby="exploration-next-title">
        <h2 id="exploration-next-title" className="text-base font-semibold text-navy">Siguiente comprobación</h2>
        <ul className="mt-3 space-y-3">{model.checks.map((check) => <li key={check} className="text-sm leading-relaxed text-navy/75">{check}</li>)}</ul>
      </section>

      {measure && <details className="border-y border-navy/10 py-4">
        <summary className="cursor-pointer text-sm font-semibold text-navy">Evidencia numérica del análisis</summary>
        <div className="mt-4 grid min-w-0 gap-6 lg:grid-cols-2">
          {dimension && <div className="min-w-0"><h3 className="text-sm font-semibold text-navy">{dimension.name}</h3><dl className="mt-2 divide-y divide-navy/10">{dimension.groups.slice().sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity)).slice(0, 20).map((row, index) => <div key={`${row.name}-${index}`} className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3 py-2 text-sm"><dt className="min-w-0 text-navy/70">{row.name}{row.records != null && <span className="block text-xs text-navy/50">{row.records.toLocaleString('es-CL')} registros</span>}{row.coverage != null && <span className="block text-xs text-navy/50">{explorationValue(row.coverage, 'porcentaje', metrics.moneda)} con costo</span>}</dt><dd className="min-w-0 text-right font-medium text-navy">{fmt(row.value)}</dd></div>)}</dl>{dimension.groups.length > 20 && <p className="mt-2 text-xs text-navy/50">Se muestran 20 grupos de {dimension.groups.length} disponibles.</p>}</div>}
          {measure.series.length > 0 && <div className="min-w-0"><h3 className="text-sm font-semibold text-navy">Serie del período</h3><dl className="mt-2 divide-y divide-navy/10">{measure.series.filter((row) => (!from || row.period.slice(0, 7) >= from.slice(0, 7)) && (!to || row.period.slice(0, 7) <= to.slice(0, 7))).slice(-24).map((row) => <div key={row.period} className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3 py-2 text-sm"><dt className="min-w-0 text-navy/70">{row.period}{row.partial && <span className="block text-xs text-navy/50">Cobertura parcial o no certificada</span>}</dt><dd className="min-w-0 text-right font-medium text-navy">{fmt(row.value)}</dd></div>)}</dl></div>}
          {!dimension && !measure.series.length && <p className="text-sm text-navy/60">No hay desglose ni serie disponible para esta medida.</p>}
        </div>
      </details>}
    </div>
  )
}
