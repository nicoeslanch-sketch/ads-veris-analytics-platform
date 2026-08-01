import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Download,
  FileCog, Loader2, Play, ShieldCheck,
} from 'lucide-react'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import PageHeader from '../components/ui/PageHeader'
import { ApiError } from '../lib/api'
import {
  activateRun, createProject, enqueuePreview, enqueueRun, getConsolidationStatus,
  getExport, getRun, inspectDataset, listDatasets, saveSources, validateProject,
} from './api'
import { useConsolidation } from './ConsolidationContext'
import { canActivateResult, TERMINAL_RUN_STATUSES, updateSource, upsertSource } from './state'
import type { DatasetInspection, DatasetOption, SourceAssignment, SourceRole } from './types'

const STEPS = [
  'Inicio', 'Archivo principal', 'Unir archivos', 'Equivalencias',
  'Validar', 'Vista previa', 'Calidad', 'Descargar',
]
const SUPPLEMENTS: SourceRole[] = ['supplement_1', 'supplement_2', 'supplement_3', 'supplement_4']
const EQUIVALENCES: SourceRole[] = ['equivalence_1', 'equivalence_2']

function statusBadge(status: string) {
  if (status === 'certified' || status === 'valid') return <Badge tone="green">Correcto</Badge>
  if (status === 'partial' || status === 'valid_with_warnings') return <Badge tone="gold">Con advertencias</Badge>
  if (status === 'blocked' || status === 'failed') return <Badge tone="coral">Bloqueado</Badge>
  return <Badge tone="teal">{status}</Badge>
}

interface SourcePickerProps {
  title: string
  description: string
  role: SourceRole
  source?: SourceAssignment
  datasets: DatasetOption[]
  inspection?: DatasetInspection
  busy: boolean
  optional?: boolean
  onChoose: (role: SourceRole, datasetId: string, label: string) => void
  onPatch: (role: SourceRole, patch: Partial<SourceAssignment>) => void
  children?: ReactNode
}

function SourcePicker({
  title, description, role, source, datasets, inspection, busy, optional,
  onChoose, onPatch, children,
}: SourcePickerProps) {
  const sheets = inspection?.sheets ?? []
  return (
    <Card className="space-y-3">
      <div><h3 className="font-semibold text-navy">{title}{optional ? <span className="ml-1 text-xs font-normal text-navy/45">(opcional)</span> : <span className="ml-1 text-coral">*</span>}</h3><p className="mt-1 text-xs text-navy/55">{description}</p></div>
      <label className="block text-xs font-semibold text-navy">Archivo
        <select value={source?.dataset_id ?? ''} disabled={busy} onChange={(event) => onChoose(role, event.target.value, title)} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 text-sm font-normal">
          <option value="">{optional ? 'No usar' : 'Selecciona un archivo'}</option>
          {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}
        </select>
      </label>
      {source && !inspection ? <p className="flex items-center gap-2 text-xs text-teal"><Loader2 className="h-3.5 w-3.5 animate-spin" />Leyendo hojas y columnas…</p> : null}
      {source && sheets.length > 1 ? <label className="block text-xs font-semibold text-navy">Hoja
        <select value={source.selected_sheet ?? sheets[0].name} onChange={(event) => onPatch(role, { selected_sheet: event.target.value })} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 text-sm font-normal">
          {sheets.map((sheet) => <option key={sheet.name}>{sheet.name}</option>)}
        </select>
      </label> : null}
      {source && inspection ? children : null}
    </Card>
  )
}

export default function GeneralConsolidationWizard({ onUseDemre }: { onUseDemre: () => void }) {
  const { project, setProject, sources, setSources, validation, setValidation, run, setRun } = useConsolidation()
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [periodLabel, setPeriodLabel] = useState('')
  const [includeHistorical, setIncludeHistorical] = useState(false)
  const [datasets, setDatasets] = useState<DatasetOption[]>([])
  const [inspections, setInspections] = useState<Record<string, DatasetInspection>>({})
  const [availability, setAvailability] = useState<'loading' | 'available' | 'disabled' | 'denied'>('loading')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const byRole = useMemo(() => new Map(sources.map((source) => [source.role, source])), [sources])
  const inspectionFor = (role: SourceRole) => {
    const datasetId = byRole.get(role)?.dataset_id
    return datasetId ? inspections[datasetId] : undefined
  }
  const columnsFor = (role: SourceRole) => {
    const source = byRole.get(role)
    const inspection = inspectionFor(role)
    if (!source || !inspection) return []
    const sheet = inspection.sheets.find((item) => item.name === source.selected_sheet) ?? inspection.sheets[0]
    return sheet?.columns ?? []
  }
  const primary = byRole.get('primary')
  const primaryColumns = columnsFor('primary')

  useEffect(() => {
    void Promise.all([listDatasets(), getConsolidationStatus()]).then(([availableDatasets, status]) => {
      setDatasets(availableDatasets)
      setAvailability(status.available ? 'available' : status.reason === 'admin_required' ? 'denied' : 'disabled')
    }).catch((reason: unknown) => {
      setAvailability('disabled')
      setError(reason instanceof Error ? reason.message : 'No se pudo comprobar la disponibilidad del servicio.')
    })
  }, [])

  useEffect(() => {
    if (!run || TERMINAL_RUN_STATUSES.has(run.status)) return
    const timer = window.setInterval(() => void getRun(run.id).then(setRun).catch(() => undefined), 2500)
    return () => window.clearInterval(timer)
  }, [run, setRun])

  const perform = async (action: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try { await action() }
    catch (reason) { setError(reason instanceof ApiError || reason instanceof Error ? reason.message : 'No se pudo completar la acción.') }
    finally { setBusy(false) }
  }

  const patchSource = (role: SourceRole, patch: Partial<SourceAssignment>) => {
    setSources(updateSource(sources, role, patch))
    setValidation(null)
  }

  const chooseSource = (role: SourceRole, datasetId: string, label: string) => {
    const required = role === 'primary'
    const next = upsertSource(sources, role, datasetId, required).map((source) =>
      source.role === role ? { ...source, label, selected_sheet: null } : source,
    )
    setSources(next)
    setValidation(null)
    if (!datasetId || inspections[datasetId]) return
    void perform(async () => {
      const inspection = await inspectDataset(datasetId)
      setInspections((current) => ({ ...current, [datasetId]: inspection }))
      const firstSheet = inspection.sheets[0]
      setSources(next.map((source) => source.role === role ? { ...source, selected_sheet: firstSheet?.name ?? null } : source))
    })
  }

  const download = async (kind: string) => {
    if (!run) return
    await perform(async () => {
      const result = await getExport(run.id, kind)
      if (result.url) window.location.assign(result.url)
      else if (result.local_path) setError(`Artefacto local: ${result.local_path}`)
    })
  }

  const readyPrimary = Boolean(project && primary?.dataset_id && primary.primary_key)

  return (
    <div>
      <PageHeader title="Consolidar y recodificar archivos" subtitle="Une Excel o CSV mediante las columnas que tú elijas, sin cambiar ni multiplicar las filas del archivo principal." />
      <ol className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8" aria-label="Pasos de consolidación">
        {STEPS.map((label, index) => <li key={label}><button type="button" disabled={index > 0 && !project} onClick={() => setStep(index)} className={`min-h-16 w-full rounded-lg border px-2 py-2 text-left text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-40 ${step === index ? 'border-teal bg-teal/10 text-navy' : 'border-navy/10 bg-white text-navy/60'}`}><span className="block text-[10px] text-teal">{index + 1}</span>{label}</button></li>)}
      </ol>

      {availability === 'disabled' ? <div role="alert" className="mb-4 rounded-lg border border-gold/35 bg-gold/10 p-3 text-sm text-navy"><strong>La función todavía no está disponible en el servidor.</strong><span className="mt-1 block text-navy/65">Activa <code>CONSOLIDATION_ENABLED=true</code> en Render. La interfaz no permitirá crear proyectos hasta que ambos lados estén habilitados.</span></div> : null}
      {availability === 'denied' ? <div role="alert" className="mb-4 rounded-lg border border-coral/30 bg-coral/10 p-3 text-sm text-coral">Esta función está en piloto y tu cuenta todavía no tiene permiso de administrador.</div> : null}
      {error ? <div role="alert" className="mb-4 flex items-start gap-2 rounded-lg border border-coral/30 bg-coral/10 p-3 text-sm text-coral"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div> : null}

      <Card className="min-h-80">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-teal">Paso {step + 1}</p><h2 className="text-lg font-semibold text-navy">{STEPS[step]}</h2></div>{project ? <Badge tone="navy">Proyecto creado</Badge> : null}</div>

        {step === 0 ? <div className="max-w-2xl space-y-5">
          <div className="rounded-lg border border-teal/20 bg-teal/[0.04] p-4 text-sm text-navy/70"><strong className="block text-navy">¿Qué se crea aquí?</strong>Un espacio de trabajo que guarda los archivos elegidos, sus claves, las uniones y las equivalencias. Escribir el nombre no procesa datos todavía.</div>
          <label className="block text-sm font-semibold text-navy">Nombre del trabajo<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Ej.: Ventas, productos y sucursales 2026" className="mt-1 w-full rounded-lg border border-navy/20 px-3 py-2 font-normal" /></label>
          <label className="block text-sm font-semibold text-navy">Periodo o versión <span className="font-normal text-navy/45">(opcional)</span><input value={periodLabel} onChange={(event) => setPeriodLabel(event.target.value)} placeholder="Ej.: 2026, julio 2026 o versión final" className="mt-1 w-full rounded-lg border border-navy/20 px-3 py-2 font-normal" /></label>
          <label className="flex items-start gap-2 text-sm text-navy/75"><input type="checkbox" checked={includeHistorical} onChange={(event) => setIncludeHistorical(event.target.checked)} className="mt-1 accent-teal" /><span><strong className="block text-navy">Combinar con datos de periodos anteriores (opcional)</strong>Actívalo solo si después seleccionarás otra base con exactamente las mismas columnas. Si no son compatibles, se generará igualmente el resultado actual y se mostrará una advertencia.</span></label>
          <div className="flex flex-wrap gap-2"><Button disabled={busy || availability !== 'available' || !name.trim()} onClick={() => void perform(async () => { const created = await createProject(name.trim(), 'general', includeHistorical, periodLabel.trim()); setProject(created); setStep(1) })}>{busy || availability === 'loading' ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileCog className="h-4 w-4" />}Crear espacio de trabajo</Button><Button variant="ghost" disabled={availability !== 'available'} onClick={onUseDemre}>Usar plantilla Educación / DEMRE 2026</Button></div>
        </div> : null}

        {step === 1 ? <div className="max-w-2xl space-y-4"><p className="text-sm text-navy/65">Este archivo define las filas del resultado. Por ejemplo, puede ser Ventas, Pedidos, Clientes o Inventario.</p><SourcePicker title="Archivo principal" description="Todas sus filas y columnas se conservarán." role="primary" source={primary} datasets={datasets} inspection={inspectionFor('primary')} busy={busy} onChoose={chooseSource} onPatch={patchSource}>{primary ? <label className="block text-xs font-semibold text-navy">Columna clave para relacionar
          <select value={primary.primary_key ?? ''} onChange={(event) => patchSource('primary', { primary_key: event.target.value })} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 text-sm font-normal"><option value="">Selecciona una columna</option>{primaryColumns.map((column) => <option key={column}>{column}</option>)}</select><span className="mt-1 block font-normal text-navy/45">Puede repetirse en el archivo principal; por ejemplo, un cliente con varias ventas.</span></label> : null}</SourcePicker><Button disabled={!readyPrimary} onClick={() => setStep(2)}>Continuar a las uniones<ChevronRight className="h-4 w-4" /></Button></div> : null}

        {step === 2 ? <div className="space-y-4"><div className="rounded-lg border border-navy/10 p-3 text-sm text-navy/65"><strong className="text-navy">Agrega solo los archivos que necesites.</strong> Cada tabla complementaria debe tener una sola fila por clave. Si una clave aparece con datos diferentes, la plataforma no la une y la informa para evitar duplicaciones.</div><div className="grid gap-4 lg:grid-cols-2">{SUPPLEMENTS.map((role, index) => {
          const source = byRole.get(role); const columns = columnsFor(role)
          return <SourcePicker key={role} title={`Archivo complementario ${index + 1}`} description="Aporta columnas al archivo principal mediante una clave común." role={role} source={source} datasets={datasets} inspection={inspectionFor(role)} busy={busy} optional onChoose={chooseSource} onPatch={patchSource}>{source ? <div className="grid gap-3 sm:grid-cols-2"><label className="block text-xs font-semibold text-navy">Clave en el principal<select value={source.primary_key ?? primary?.primary_key ?? ''} onChange={(event) => patchSource(role, { primary_key: event.target.value })} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 text-sm font-normal"><option value="">Selecciona</option>{primaryColumns.map((column) => <option key={column}>{column}</option>)}</select></label><label className="block text-xs font-semibold text-navy">Clave en este archivo<select value={source.source_key ?? ''} onChange={(event) => patchSource(role, { source_key: event.target.value, primary_key: source.primary_key ?? primary?.primary_key })} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 text-sm font-normal"><option value="">Selecciona</option>{columns.map((column) => <option key={column}>{column}</option>)}</select></label><label className="block text-xs font-semibold text-navy sm:col-span-2">Prefijo si hay nombres repetidos <span className="font-normal text-navy/45">(opcional)</span><input value={source.prefix ?? ''} onChange={(event) => patchSource(role, { prefix: event.target.value })} placeholder="Ej.: producto" className="mt-1 w-full rounded-lg border border-navy/20 px-2 py-2 text-sm font-normal" /></label></div> : null}</SourcePicker>
        })}</div>{includeHistorical ? <SourcePicker title="Datos de periodos anteriores" description="Se apilarán debajo del resultado solo si las columnas coinciden exactamente." role="historical" source={byRole.get('historical')} datasets={datasets} inspection={inspectionFor('historical')} busy={busy} optional onChoose={chooseSource} onPatch={patchSource} /> : null}<Button disabled={!readyPrimary} onClick={() => setStep(3)}>Continuar<ChevronRight className="h-4 w-4" /></Button></div> : null}

        {step === 3 ? <div className="space-y-4"><p className="text-sm text-navy/65">Una tabla de equivalencias traduce códigos sin borrar el valor original. Ejemplo: <code>1 → Activo</code>. El resultado se guarda en una columna nueva.</p><div className="grid gap-4 lg:grid-cols-2">{EQUIVALENCES.map((role, index) => {
          const source = byRole.get(role); const columns = columnsFor(role)
          return <SourcePicker key={role} title={`Tabla de equivalencias ${index + 1}`} description="Debe contener una columna de código y otra con su significado." role={role} source={source} datasets={datasets} inspection={inspectionFor(role)} busy={busy} optional onChoose={chooseSource} onPatch={patchSource}>{source ? <div className="grid gap-3"><label className="block text-xs font-semibold text-navy">Columna del resultado a traducir<select value={source.target_column ?? ''} onChange={(event) => patchSource(role, { target_column: event.target.value })} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 text-sm font-normal"><option value="">Selecciona</option>{primaryColumns.map((column) => <option key={column}>{column}</option>)}</select></label><div className="grid gap-3 sm:grid-cols-2"><label className="block text-xs font-semibold text-navy">Columna de código<select value={source.source_key ?? ''} onChange={(event) => patchSource(role, { source_key: event.target.value })} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 text-sm font-normal"><option value="">Selecciona</option>{columns.map((column) => <option key={column}>{column}</option>)}</select></label><label className="block text-xs font-semibold text-navy">Columna con significado<select value={source.value_column ?? ''} onChange={(event) => patchSource(role, { value_column: event.target.value })} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 text-sm font-normal"><option value="">Selecciona</option>{columns.map((column) => <option key={column}>{column}</option>)}</select></label></div><label className="block text-xs font-semibold text-navy">Nombre de la columna nueva <span className="font-normal text-navy/45">(opcional)</span><input value={source.output_column ?? ''} onChange={(event) => patchSource(role, { output_column: event.target.value })} placeholder="Ej.: estado_descripcion" className="mt-1 w-full rounded-lg border border-navy/20 px-2 py-2 text-sm font-normal" /></label></div> : null}</SourcePicker>
        })}</div><Button disabled={!readyPrimary || busy} onClick={() => void perform(async () => { if (!project) return; const saved = await saveSources(project.id, sources); setProject(saved); setValidation(await validateProject(project.id)); setStep(4) })}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}Guardar configuración y validar</Button></div> : null}

        {step === 4 ? <div className="space-y-4"><p className="text-sm text-navy/65">Comprueba que exista un archivo principal, que las claves estén elegidas y que cada equivalencia tenga sus tres columnas configuradas.</p><Button disabled={busy || !project} onClick={() => void perform(async () => { if (!project) return; const saved = await saveSources(project.id, sources); setProject(saved); setValidation(await validateProject(project.id)) })}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}Volver a validar</Button>{validation ? <div className="rounded-lg border border-navy/10 p-4">{statusBadge(validation.status)}<p className="mt-2 text-sm text-navy/70">{validation.source_count} archivos configurados</p>{validation.warnings.map((warning) => <p key={warning} className="mt-1 text-sm text-gold">Advertencia: {warning}</p>)}{validation.blocking.map((issue) => <p key={issue} className="mt-1 text-sm text-coral">Falta: {issue}</p>)}</div> : null}<Button disabled={!validation || validation.status === 'blocked'} onClick={() => setStep(5)}>Preparar vista previa<ChevronRight className="h-4 w-4" /></Button></div> : null}

        {step === 5 ? <div className="space-y-4"><p className="text-sm text-navy/65">Procesa una muestra segura antes de generar las descargas. Las columnas que parecen identificadores o datos personales se excluyen de la tabla de muestra.</p><Button disabled={busy || !project || validation?.status === 'blocked'} onClick={() => void perform(async () => { if (project) setRun(await enqueuePreview(project.id)) })}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}Generar vista previa</Button>{run ? <div className="flex items-center gap-2">{statusBadge(run.status)}{TERMINAL_RUN_STATUSES.has(run.status) ? null : <Loader2 className="h-4 w-4 animate-spin text-teal" />}</div> : null}{run?.report?.preview?.length ? <div className="overflow-x-auto rounded-lg border border-navy/10"><table className="w-full text-left text-xs"><thead><tr className="bg-navy/5">{Object.keys(run.report.preview[0]).map((column) => <th key={column} className="px-3 py-2 font-semibold">{column}</th>)}</tr></thead><tbody>{run.report.preview.map((row, index) => <tr key={index} className="border-t border-navy/10">{Object.keys(run.report!.preview![0]).map((column) => <td key={column} className="max-w-60 px-3 py-2 text-navy/70">{row[column] || '—'}</td>)}</tr>)}</tbody></table></div> : null}</div> : null}

        {step === 6 ? <div className="space-y-4">{run?.report ? <><div className="grid gap-3 sm:grid-cols-3"><Card><p className="text-xs text-navy/50">Filas principales</p><p className="text-xl font-semibold">{run.report.row_counts?.primary ?? '—'}</p></Card><Card><p className="text-xs text-navy/50">Filas finales</p><p className="text-xl font-semibold">{run.report.row_counts?.annual ?? '—'}</p></Card><Card><p className="text-xs text-navy/50">Tiempo</p><p className="text-xl font-semibold">{run.report.timings_ms?.total ? `${Math.round(run.report.timings_ms.total / 1000)} s` : '—'}</p></Card></div><ul className="space-y-2">{run.report.issues?.map((issue) => <li key={issue.code} className="rounded-lg border border-navy/10 p-3 text-sm">{statusBadge(issue.severity)} <span className="ml-2 text-navy/70">{issue.message}{issue.count ? ` (${issue.count})` : ''}</span></li>)}</ul></> : <p className="text-sm text-navy/60">Genera la vista previa para revisar coincidencias, claves ambiguas y valores sin equivalencia.</p>}</div> : null}

        {step === 7 ? <div className="space-y-4"><p className="text-sm text-navy/65">Genera la base consolidada, la auditoría y el manifiesto de trazabilidad.</p><Button disabled={busy || !project} onClick={() => void perform(async () => { if (project) setRun(await enqueueRun(project.id)) })}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}Generar archivos finales</Button>{run && TERMINAL_RUN_STATUSES.has(run.status) ? <div className="space-y-3"><div>{statusBadge(run.status)}</div><div className="flex flex-wrap gap-2">{run.artifacts?.map((artifact) => <Button key={artifact.kind} variant="ghost" onClick={() => void download(artifact.kind)}><Download className="h-4 w-4" />{artifact.kind === 'annual' ? 'Base consolidada' : artifact.kind === 'audit' ? 'Auditoría' : artifact.kind === 'historical' ? 'Base histórica' : 'Manifiesto'}</Button>)}</div><Button disabled={!canActivateResult(run.status, Boolean(run.artifacts?.some((item) => item.kind === 'annual')))} onClick={() => void perform(async () => { await activateRun(run.id, `${name} — resultado`); setError('Resultado registrado como dataset derivado.') })}>Usar resultado en la plataforma</Button></div> : null}</div> : null}
      </Card>

      <div className="mt-4 flex justify-between gap-3"><Button variant="ghost" disabled={step === 0} onClick={() => setStep((value) => Math.max(0, value - 1))}><ChevronLeft className="h-4 w-4" />Anterior</Button><Button variant="ghost" disabled={step === STEPS.length - 1 || !project} onClick={() => setStep((value) => Math.min(STEPS.length - 1, value + 1))}>Siguiente<ChevronRight className="h-4 w-4" /></Button></div>
    </div>
  )
}
