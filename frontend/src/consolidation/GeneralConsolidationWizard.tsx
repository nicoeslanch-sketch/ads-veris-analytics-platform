import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Download, FilePlus2,
  Loader2, Play, RefreshCw, ShieldCheck, Trash2, UploadCloud,
} from 'lucide-react'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import PageHeader from '../components/ui/PageHeader'
import { ApiError } from '../lib/api'
import { uploadConsolidationDataset } from '../lib/datasets'
import {
  activateRun, createProject, detectDatasets, enqueuePreview, enqueueRun,
  getConsolidationStatus, getExport, getRun, listDatasets, saveSources, validateProject,
} from './api'
import { useConsolidation } from './ConsolidationContext'
import { canActivateResult, TERMINAL_RUN_STATUSES } from './state'
import type { DatasetOption, DetectionProposal, SourceAssignment, SourceRole } from './types'

export const CONSOLIDATION_STEPS = ['Cargar', 'Revisar', 'Comprobar', 'Obtener resultado'] as const

const FRIENDLY_ROLES: Array<{ value: SourceRole | ''; label: string }> = [
  { value: '', label: 'No usar por ahora' },
  { value: 'primary', label: 'Archivo base' },
  { value: 'supplement_1', label: 'Agregar información 1' },
  { value: 'supplement_2', label: 'Agregar información 2' },
  { value: 'supplement_3', label: 'Agregar información 3' },
  { value: 'supplement_4', label: 'Agregar información 4' },
  { value: 'equivalence_1', label: 'Tabla de equivalencias 1' },
  { value: 'equivalence_2', label: 'Tabla de equivalencias 2' },
  { value: 'historical', label: 'Periodos anteriores' },
]

const DEMRE_LABELS: Record<string, string> = {
  matricula: 'Matrícula: archivo base', archivo_b: 'Antecedentes demográficos y educacionales',
  archivo_c: 'Notas, ranking y pruebas', archivo_d: 'Preferencias y selección',
  oferta: 'Carreras, instituciones y sedes', historica: 'Periodos anteriores',
  codebook_matricula: 'Libro de vía y tipo de matrícula', codebook_b: 'Libro de antecedentes',
  codebook_c: 'Libro de pruebas', codebook_d: 'Libro de estados y preferencias',
}

const DEMRE_ROLE_OPTIONS: Array<{ value: SourceRole | ''; label: string }> = [
  { value: '', label: 'No usar por ahora' },
  ...Object.entries(DEMRE_LABELS).map(([value, label]) => ({ value: value as SourceRole, label })),
]

const STAGE_LABELS: Record<string, string> = {
  download_sources: 'Preparando archivos', read_matricula: 'Leyendo el archivo base',
  read_primary: 'Leyendo el archivo base', read_archivo_b: 'Relacionando antecedentes',
  read_archivo_c: 'Relacionando pruebas', reduce_archivo_d: 'Resolviendo preferencias',
  read_filter_oferta: 'Filtrando la oferta del periodo', mapping: 'Agregando columnas seguras',
  parse_codebooks: 'Traduciendo códigos', consolidation: 'Construyendo el resultado',
  quality_control: 'Comprobando calidad', export_annual: 'Creando la base descargable',
  export_audit: 'Creando el informe de calidad', cleanup_temporaries: 'Limpiando archivos temporales',
}

const ARTIFACT_LABELS: Record<string, string> = {
  annual: 'Descargar base consolidada', historical: 'Descargar base histórica consolidada',
  audit: 'Descargar informe de calidad', manifest: 'Descargar detalle técnico',
}

interface UploadItem {
  id: string
  file: File
  progress: number
  status: 'uploading' | 'done' | 'failed' | 'cancelled'
  error?: string
  datasetId?: string
  controller: AbortController
}

interface FileDecision {
  role: SourceRole | ''
  sheet?: string | null
  primaryKey?: string
  relatedKey?: string
  targetColumn?: string
  valueColumn?: string
  outputColumn?: string
}

function statusBadge(status: string) {
  if (status === 'certified' || status === 'valid') return <Badge tone="green">Correcto</Badge>
  if (status === 'partial' || status === 'valid_with_warnings') return <Badge tone="gold">Con advertencias</Badge>
  if (status === 'blocked' || status === 'failed') return <Badge tone="coral">Necesita corrección</Badge>
  return <Badge tone="teal">Procesando</Badge>
}

function confidenceLabel(value: number) {
  if (value >= 0.85) return 'Alta'
  if (value >= 0.55) return 'Media'
  return 'Baja'
}

function firstMatching(columns: string[], markers: string[]) {
  return columns.find((column) => markers.some((marker) => column.toLocaleLowerCase().includes(marker))) ?? ''
}

function initialDecisions(proposal: DetectionProposal): Record<string, FileDecision> {
  return Object.fromEntries(proposal.files.map((file) => {
    const key = file.suggested_keys.length === 1 ? file.suggested_keys[0] : undefined
    const role = file.suggested_role ?? ''
    const isEquivalence = role.startsWith('equivalence_')
    return [file.dataset_id, {
      role,
      sheet: file.sheet,
      primaryKey: role === 'primary' ? file.suggested_keys[0]?.base : key?.base,
      relatedKey: key?.related || (isEquivalence ? firstMatching(file.columns, ['cód', 'cod', 'id', 'clave']) : ''),
      targetColumn: isEquivalence ? key?.base : '',
      valueColumn: isEquivalence ? firstMatching(file.columns, ['descrip', 'nombre', 'detalle', 'label']) : '',
    }]
  }))
}

export default function GeneralConsolidationWizard() {
  const { project, setProject, setSources, validation, setValidation, run, setRun } = useConsolidation()
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [period, setPeriod] = useState('2026')
  const [datasets, setDatasets] = useState<DatasetOption[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [uploads, setUploads] = useState<UploadItem[]>([])
  const [proposal, setProposal] = useState<DetectionProposal | null>(null)
  const [template, setTemplate] = useState<'general' | 'demre_2026'>('general')
  const [decisions, setDecisions] = useState<Record<string, FileDecision>>({})
  const [busy, setBusy] = useState(false)
  const [availability, setAvailability] = useState<'loading' | 'available' | 'disabled' | 'denied'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [previewPage, setPreviewPage] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const perform = useCallback(async (action: () => Promise<void>) => {
    setBusy(true); setError(null); setNotice(null)
    try { await action() }
    catch (reason) { setError(reason instanceof ApiError || reason instanceof Error ? reason.message : 'No se pudo completar la acción.') }
    finally { setBusy(false) }
  }, [])

  useEffect(() => {
    void Promise.all([listDatasets(), getConsolidationStatus()]).then(([available, status]) => {
      setDatasets(available)
      setAvailability(status.available ? 'available' : status.reason === 'admin_required' ? 'denied' : 'disabled')
    }).catch((reason: unknown) => {
      setAvailability('disabled'); setError(reason instanceof Error ? reason.message : 'No se pudo abrir el asistente.')
    })
  }, [])

  useEffect(() => {
    if (!run || TERMINAL_RUN_STATUSES.has(run.status)) return
    const timer = window.setInterval(() => void getRun(run.id).then(setRun).catch(() => undefined), 2000)
    return () => window.clearInterval(timer)
  }, [run, setRun])

  const uploadOne = useCallback((item: UploadItem) => {
    setUploads((current) => [...current.filter((entry) => entry.id !== item.id), item])
    void uploadConsolidationDataset(item.file, {
      signal: item.controller.signal,
      onProgress: (progress) => setUploads((current) => current.map((entry) => entry.id === item.id ? { ...entry, progress } : entry)),
    }).then((dataset) => {
      setDatasets((current) => [dataset, ...current.filter((entry) => entry.id !== dataset.id)])
      setSelectedIds((current) => Array.from(new Set([...current, dataset.id])))
      setUploads((current) => current.map((entry) => entry.id === item.id ? { ...entry, status: 'done', progress: 100, datasetId: dataset.id } : entry))
      if (!name.trim()) setName(`${period ? `${period} · ` : ''}${item.file.name.replace(/\.(csv|xlsx)$/i, '')}`)
    }).catch((reason: unknown) => {
      const cancelled = reason instanceof DOMException && reason.name === 'AbortError'
      setUploads((current) => current.map((entry) => entry.id === item.id ? {
        ...entry, status: cancelled ? 'cancelled' : 'failed', error: reason instanceof Error ? reason.message : 'Falló la carga.',
      } : entry))
    })
  }, [name, period])

  const addFiles = (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      const item: UploadItem = { id: crypto.randomUUID(), file, progress: 0, status: 'uploading', controller: new AbortController() }
      uploadOne(item)
    }
  }

  const retryUpload = (item: UploadItem) => uploadOne({ ...item, progress: 0, status: 'uploading', error: undefined, controller: new AbortController() })
  const removeUpload = (item: UploadItem) => {
    if (item.status === 'uploading') item.controller.abort()
    if (item.datasetId) setSelectedIds((current) => current.filter((id) => id !== item.datasetId))
    setUploads((current) => current.filter((entry) => entry.id !== item.id))
  }

  const continueToReview = () => void perform(async () => {
    if (!selectedIds.length) throw new Error('Selecciona o sube al menos un archivo.')
    const detected = await detectDatasets(selectedIds)
    setProposal(detected); setTemplate(detected.template); setDecisions(initialDecisions(detected)); setStep(1)
    if (!name.trim()) setName(`${period ? `${period} · ` : ''}Consolidación de ${selectedIds.length} archivos`)
  })

  const changeRole = (datasetId: string, role: SourceRole | '') => {
    setDecisions((current) => {
      const cleared = Object.fromEntries(Object.entries(current).map(([id, value]) => [id, id !== datasetId && role && value.role === role ? { ...value, role: '' as const } : value]))
      return { ...cleared, [datasetId]: { ...cleared[datasetId], role } }
    })
  }

  const assignments = useMemo<SourceAssignment[]>(() => {
    if (!proposal) return []
    return proposal.files.flatMap((file) => {
      const decision = decisions[file.dataset_id]
      if (!decision?.role) return []
      const equivalence = decision.role.startsWith('equivalence_')
      return [{
        dataset_id: file.dataset_id, role: decision.role,
        required: decision.role === 'primary' || decision.role === 'matricula',
        selected_sheet: decision.sheet ?? file.sheet ?? null, label: file.name,
        primary_key: decision.role === 'primary' ? decision.primaryKey : decision.primaryKey,
        source_key: decision.relatedKey,
        target_column: decision.targetColumn,
        value_column: decision.valueColumn,
        output_column: equivalence ? decision.outputColumn : undefined,
      }]
    })
  }, [decisions, proposal])

  const preparePreview = () => void perform(async () => {
    if (!proposal) return
    const requiredRole = template === 'demre_2026' ? 'matricula' : 'primary'
    if (!assignments.some((source) => source.role === requiredRole)) throw new Error('Confirma cuál archivo conservará las filas del resultado.')
    const created = project ?? await createProject(name.trim() || 'Consolidación', template, assignments.some((source) => ['historical', 'historica'].includes(source.role)), period)
    setProject(created); setSources(assignments)
    const saved = await saveSources(created.id, assignments)
    setProject(saved)
    const checked = await validateProject(created.id)
    setValidation(checked); setStep(2)
    if (checked.status !== 'blocked') setRun(await enqueuePreview(created.id))
  })

  const download = (kind: string) => run && void perform(async () => {
    const result = await getExport(run.id, kind)
    if (result.url) window.location.assign(result.url)
    else if (result.local_path) setNotice(`Resultado local: ${result.local_path}`)
  })

  const preview = run?.report?.preview ?? []
  const previewColumns = preview[0] ? Object.keys(preview[0]) : []
  const visiblePreview = preview.slice(previewPage * 10, previewPage * 10 + 10)

  return <div>
    <PageHeader title="Consolidar y recodificar archivos" subtitle="Conservaremos las filas del archivo base y añadiremos información solo cuando las relaciones sean seguras." />
    <ol className="mb-6 grid grid-cols-2 gap-2 lg:grid-cols-4" aria-label="Pasos de consolidación">
      {CONSOLIDATION_STEPS.map((label, index) => <li key={label}><button type="button" onClick={() => index <= step && setStep(index)} disabled={index > step} className={`min-h-16 w-full rounded-xl border px-4 py-3 text-left text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-45 ${step === index ? 'border-teal bg-teal/10 text-navy shadow-sm' : 'border-navy/10 bg-white text-navy/60'}`}><span className="mr-2 text-xs text-teal">{index + 1}</span>{label}</button></li>)}
    </ol>

    {availability === 'disabled' ? <div role="alert" className="mb-4 rounded-xl border border-gold/35 bg-gold/10 p-4 text-sm text-navy">La consolidación todavía no está habilitada en el servidor.</div> : null}
    {availability === 'denied' ? <div role="alert" className="mb-4 rounded-xl border border-coral/30 bg-coral/10 p-4 text-sm text-coral">Esta función piloto está disponible solo para administradores.</div> : null}
    {notice ? <div role="status" className="mb-4 flex items-start gap-2 rounded-xl border border-teal/30 bg-teal/10 p-4 text-sm text-teal"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />{notice}</div> : null}
    {error ? <div role="alert" className="mb-4 flex items-start gap-2 rounded-xl border border-coral/30 bg-coral/10 p-4 text-sm text-coral"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div> : null}

    <Card className="min-h-96">
      <div className="mb-6"><p className="text-xs font-semibold uppercase tracking-wide text-teal">Paso {step + 1} de 4</p><h2 className="text-xl font-semibold text-navy">{CONSOLIDATION_STEPS[step]}</h2></div>

      {step === 0 ? <div className="space-y-6">
        <div className="grid gap-4 md:grid-cols-2"><label className="text-sm font-semibold text-navy">Nombre del trabajo<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Se completará automáticamente" className="mt-1 w-full rounded-lg border border-navy/20 px-3 py-2 font-normal" /></label><label className="text-sm font-semibold text-navy">Periodo o versión<input value={period} onChange={(event) => setPeriod(event.target.value)} placeholder="Ej.: 2026" className="mt-1 w-full rounded-lg border border-navy/20 px-3 py-2 font-normal" /></label></div>
        <div role="button" tabIndex={0} onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && inputRef.current?.click()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); addFiles(event.dataTransfer.files) }} onClick={() => inputRef.current?.click()} className="flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-teal/40 bg-teal/[0.035] p-6 text-center focus:outline-none focus:ring-2 focus:ring-teal">
          <UploadCloud className="mb-3 h-9 w-9 text-teal" /><p className="font-semibold text-navy">Sube los archivos que quieres unir o recodificar</p><p className="mt-1 max-w-2xl text-sm text-navy/60">Puedes cargar todos de una vez. La plataforma revisará sus columnas y te propondrá cómo relacionarlos.</p><input ref={inputRef} type="file" multiple accept=".csv,.xlsx" className="sr-only" onChange={(event) => event.target.files && addFiles(event.target.files)} /></div>
        {uploads.length ? <div className="grid gap-3 md:grid-cols-2">{uploads.map((item) => <div key={item.id} className="rounded-xl border border-navy/10 p-3"><div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="truncate text-sm font-semibold text-navy">{item.file.name}</p><p className="text-xs text-navy/50">{(item.file.size / 1_048_576).toFixed(1)} MB · {item.status === 'done' ? 'Listo' : item.status === 'failed' ? 'Falló' : item.status === 'cancelled' ? 'Cancelado' : `Subiendo ${item.progress}%`}</p></div><Button variant="ghost" onClick={() => removeUpload(item)} aria-label={`Quitar ${item.file.name}`}><Trash2 className="h-4 w-4" /></Button></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-navy/10"><div className={`h-full ${item.status === 'failed' ? 'bg-coral' : 'bg-teal'}`} style={{ width: `${item.progress}%` }} /></div>{item.error ? <p className="mt-2 text-xs text-coral">{item.error}</p> : null}{item.status === 'uploading' ? <Button variant="ghost" onClick={() => item.controller.abort()}>Cancelar</Button> : null}{['failed', 'cancelled'].includes(item.status) ? <Button variant="ghost" onClick={() => retryUpload(item)}><RefreshCw className="h-4 w-4" />Reintentar</Button> : null}</div>)}</div> : null}
        <details className="rounded-xl border border-navy/10 p-4"><summary className="cursor-pointer text-sm font-semibold text-navy">Elegir documentos ya cargados</summary><div className="mt-3 grid max-h-56 gap-2 overflow-y-auto md:grid-cols-2">{datasets.map((dataset) => <label key={dataset.id} className="flex items-center gap-2 rounded-lg border border-navy/10 p-2 text-sm text-navy/75"><input type="checkbox" checked={selectedIds.includes(dataset.id)} onChange={() => setSelectedIds((current) => current.includes(dataset.id) ? current.filter((id) => id !== dataset.id) : [...current, dataset.id])} className="accent-teal" /><span className="truncate">{dataset.name}</span></label>)}</div></details>
        <Button disabled={busy || availability !== 'available' || !selectedIds.length || uploads.some((item) => item.status === 'uploading')} onClick={continueToReview}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ChevronRight className="h-4 w-4" />}Revisar archivos</Button>
      </div> : null}

      {step === 1 && proposal ? <div className="space-y-5">
        {proposal.template === 'demre_2026' ? <div className="rounded-xl border border-teal/30 bg-teal/[0.05] p-4"><p className="font-semibold text-navy">Detectamos una consolidación Educación / DEMRE 2026</p><p className="mt-1 text-sm text-navy/65">Podemos configurar automáticamente Matrícula, B, C, D, Oferta y sus libros de códigos.</p><div className="mt-3 flex flex-wrap gap-2"><Button onClick={() => setTemplate('demre_2026')}><CheckCircle2 className="h-4 w-4" />Usar configuración detectada</Button><Button variant="ghost" onClick={() => setTemplate('demre_2026')}>Revisar manualmente</Button><Button variant="ghost" onClick={() => { setTemplate('general'); setDecisions(initialDecisions({ ...proposal, template: 'general', files: proposal.files.map((file) => ({ ...file, suggested_role: file.detected_role === 'matricula' ? 'primary' : null })) })) }}>Usar modo general</Button></div></div> : <p className="text-sm text-navy/65">Revisa la propuesta. Solo necesitas intervenir cuando la confianza sea media o baja.</p>}
        {proposal.questions.map((question) => <div key={question} className="rounded-lg border border-gold/30 bg-gold/10 p-3 text-sm text-navy">{question}</div>)}
        <div className="grid gap-4 xl:grid-cols-2">{proposal.files.map((file) => {
          const decision = decisions[file.dataset_id] ?? { role: '' }
          const related = decision.role.startsWith('supplement_')
          const equivalence = decision.role.startsWith('equivalence_')
          const roleOptions = template === 'demre_2026' ? DEMRE_ROLE_OPTIONS : FRIENDLY_ROLES
          return <Card key={file.dataset_id} className="space-y-3"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><h3 className="truncate font-semibold text-navy">{file.name}</h3><p className="text-xs text-navy/55">{file.kind} · {file.sheet || 'Sin hoja'} · ~{(file.approximate_rows ?? 0).toLocaleString('es-CL')} filas · {file.column_count} columnas</p></div><Badge tone={file.confidence >= .85 ? 'green' : file.confidence >= .55 ? 'gold' : 'coral'}>Confianza {confidenceLabel(file.confidence)}</Badge></div><p className="text-sm font-medium text-navy/75">{template === 'demre_2026' && decision.role ? DEMRE_LABELS[decision.role] ?? file.role_label : file.role_label}</p><label className="block text-xs font-semibold text-navy">Función<select value={decision.role} onChange={(event) => changeRole(file.dataset_id, event.target.value as SourceRole | '')} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 text-sm font-normal">{roleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>{file.warnings.map((warning) => <p key={warning} className="text-xs text-gold">{warning}</p>)}<details className="rounded-lg border border-navy/10 p-3"><summary className="cursor-pointer text-xs font-semibold text-navy">Opciones avanzadas</summary><div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="text-xs font-semibold text-navy">Hoja<input value={decision.sheet ?? ''} onChange={(event) => setDecisions((current) => ({ ...current, [file.dataset_id]: { ...decision, sheet: event.target.value } }))} className="mt-1 w-full rounded-lg border border-navy/20 px-2 py-2 font-normal" /></label>{(decision.role === 'primary' || related) ? <label className="text-xs font-semibold text-navy">Columna en el archivo base<select value={decision.primaryKey ?? ''} onChange={(event) => setDecisions((current) => ({ ...current, [file.dataset_id]: { ...decision, primaryKey: event.target.value } }))} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 font-normal"><option value="">Selecciona</option>{(decision.role === 'primary' ? file.columns : proposal.files.find((candidate) => decisions[candidate.dataset_id]?.role === 'primary')?.columns ?? []).map((column) => <option key={column}>{column}</option>)}</select></label> : null}{related ? <label className="text-xs font-semibold text-navy">Columna en este archivo<select value={decision.relatedKey ?? ''} onChange={(event) => setDecisions((current) => ({ ...current, [file.dataset_id]: { ...decision, relatedKey: event.target.value } }))} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 font-normal"><option value="">Selecciona</option>{file.columns.map((column) => <option key={column}>{column}</option>)}</select></label> : null}{equivalence ? <><label className="text-xs font-semibold text-navy">Columna del resultado a traducir<select value={decision.targetColumn ?? ''} onChange={(event) => setDecisions((current) => ({ ...current, [file.dataset_id]: { ...decision, targetColumn: event.target.value } }))} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 font-normal"><option value="">Selecciona</option>{(proposal.files.find((candidate) => decisions[candidate.dataset_id]?.role === 'primary')?.columns ?? []).map((column) => <option key={column}>{column}</option>)}</select></label><label className="text-xs font-semibold text-navy">Código en esta tabla<select value={decision.relatedKey ?? ''} onChange={(event) => setDecisions((current) => ({ ...current, [file.dataset_id]: { ...decision, relatedKey: event.target.value } }))} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 font-normal"><option value="">Selecciona</option>{file.columns.map((column) => <option key={column}>{column}</option>)}</select></label><label className="text-xs font-semibold text-navy">Descripción<select value={decision.valueColumn ?? ''} onChange={(event) => setDecisions((current) => ({ ...current, [file.dataset_id]: { ...decision, valueColumn: event.target.value } }))} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 font-normal"><option value="">Selecciona</option>{file.columns.map((column) => <option key={column}>{column}</option>)}</select></label><label className="text-xs font-semibold text-navy">Nombre de la columna nueva<input value={decision.outputColumn ?? ''} onChange={(event) => setDecisions((current) => ({ ...current, [file.dataset_id]: { ...decision, outputColumn: event.target.value } }))} placeholder="Ej.: estado_descripcion" className="mt-1 w-full rounded-lg border border-navy/20 px-2 py-2 font-normal" /></label></> : null}</div></details></Card>
        })}</div>
        <Button disabled={busy} onClick={preparePreview}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}Comprobar resultado</Button>
      </div> : null}

      {step === 2 ? <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3">{validation ? statusBadge(validation.status) : <Badge tone="teal">Validando</Badge>}{run && !TERMINAL_RUN_STATUSES.has(run.status) ? <span className="flex items-center gap-2 text-sm text-teal"><Loader2 className="h-4 w-4 animate-spin" />Preparando una muestra segura…</span> : null}</div>
        {validation?.blocking.map((message) => <div key={message} className="rounded-lg border border-coral/30 bg-coral/10 p-3 text-sm text-coral"><strong>Qué ocurrió:</strong> {message} <span className="block text-navy/65">No procesaremos hasta corregirlo para evitar un resultado incompleto.</span></div>)}
        {validation?.warnings.map((message) => <div key={message} className="rounded-lg border border-gold/30 bg-gold/10 p-3 text-sm text-navy"><strong>Advertencia:</strong> {message} <span className="block text-navy/65">La plataforma continuará, conservará las filas base y dejará constancia en la auditoría.</span></div>)}
        {run?.report ? <><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Card><p className="text-xs text-navy/50">Filas del resultado</p><p className="text-xl font-semibold text-navy">{run.report.row_counts?.annual?.toLocaleString('es-CL') ?? '—'}</p></Card><Card><p className="text-xs text-navy/50">Columnas originales</p><p className="text-xl font-semibold text-navy">{run.report.row_counts?.original_columns?.toLocaleString('es-CL') ?? '—'}</p></Card><Card><p className="text-xs text-navy/50">Columnas agregadas</p><p className="text-xl font-semibold text-navy">{run.report.row_counts?.added_columns?.toLocaleString('es-CL') ?? '—'}</p></Card><Card><p className="text-xs text-navy/50">Archivos relacionados</p><p className="text-xl font-semibold text-navy">{run.report.row_counts?.files_related ?? run.report.relationship_summary?.length ?? 0}</p></Card><Card><p className="text-xs text-navy/50">Filas sin coincidencia</p><p className="text-xl font-semibold text-navy">{run.report.row_counts?.unmatched_rows?.toLocaleString('es-CL') ?? 0}</p></Card><Card><p className="text-xs text-navy/50">Claves ambiguas</p><p className="text-xl font-semibold text-navy">{run.report.row_counts?.ambiguous_keys?.toLocaleString('es-CL') ?? 0}</p></Card><Card><p className="text-xs text-navy/50">Códigos traducidos / sin equivalencia</p><p className="text-xl font-semibold text-navy">{run.report.row_counts?.codes_translated?.toLocaleString('es-CL') ?? 0} / {run.report.row_counts?.codes_unmapped?.toLocaleString('es-CL') ?? 0}</p></Card><Card><p className="text-xs text-navy/50">Estado</p><div className="mt-1">{statusBadge(run.status)}</div></Card></div>{run.report.issues?.map((issue) => <div key={issue.code} className="rounded-lg border border-navy/10 p-3 text-sm text-navy/75">{statusBadge(issue.severity)} <span className="ml-2">{issue.message}{issue.count ? ` (${issue.count.toLocaleString('es-CL')})` : ''}</span></div>)}</> : null}
        {visiblePreview.length ? <div><div className="overflow-x-auto rounded-xl border border-navy/10"><table className="w-full text-left text-xs"><thead><tr className="bg-navy/5">{previewColumns.map((column) => <th key={column} className="whitespace-nowrap px-3 py-2 font-semibold text-navy">{column}</th>)}</tr></thead><tbody>{visiblePreview.map((row, index) => <tr key={index} className="border-t border-navy/10">{previewColumns.map((column) => <td key={column} className="max-w-64 truncate px-3 py-2 text-navy/70">{row[column] || '—'}</td>)}</tr>)}</tbody></table></div><div className="mt-2 flex items-center justify-end gap-2"><Button variant="ghost" disabled={previewPage === 0} onClick={() => setPreviewPage((value) => value - 1)}>Anterior</Button><span className="text-xs text-navy/55">Página {previewPage + 1}</span><Button variant="ghost" disabled={(previewPage + 1) * 10 >= preview.length} onClick={() => setPreviewPage((value) => value + 1)}>Siguiente</Button></div></div> : null}
        <div className="flex flex-wrap gap-2"><Button variant="ghost" onClick={() => setStep(1)}><ChevronLeft className="h-4 w-4" />Corregir configuración</Button><Button disabled={!run || !TERMINAL_RUN_STATUSES.has(run.status) || run.status === 'blocked' || run.status === 'failed'} onClick={() => setStep(3)}>Obtener resultado<ChevronRight className="h-4 w-4" /></Button></div>
      </div> : null}

      {step === 3 ? <div className="space-y-5"><div className="rounded-xl border border-teal/20 bg-teal/[0.04] p-4 text-sm text-navy/70">Procesaremos los archivos originales sin modificarlos. El worker conserva una sola ejecución activa, controla memoria y disco y registra huellas SHA-256.</div><Button disabled={busy || !project || (run ? !TERMINAL_RUN_STATUSES.has(run.status) : false)} onClick={() => void perform(async () => { if (project) setRun(await enqueueRun(project.id)) })}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}Procesar archivos</Button>{run && !TERMINAL_RUN_STATUSES.has(run.status) ? <div className="space-y-3 rounded-lg border border-teal/20 p-4 text-sm text-teal"><div className="flex items-center gap-2"><Loader2 className="h-5 w-5 animate-spin" />Worker procesando y comprobando el resultado…</div>{run.events?.length ? <ol className="grid gap-2 sm:grid-cols-2">{Array.from(new Map(run.events.map((event) => [event.stage, event])).values()).map((event) => <li key={event.stage} className="flex items-center gap-2 text-xs text-navy/65">{event.status === 'completed' ? <CheckCircle2 className="h-3.5 w-3.5 text-teal" /> : <Loader2 className="h-3.5 w-3.5 animate-spin text-teal" />}{STAGE_LABELS[event.stage] ?? event.stage}</li>)}</ol> : null}</div> : null}{run && TERMINAL_RUN_STATUSES.has(run.status) ? <div className="space-y-4"><div className="flex items-center gap-3">{statusBadge(run.status)}<span className="text-sm text-navy/60">{run.report?.timings_ms?.total ? `${Math.round(run.report.timings_ms.total / 1000)} segundos` : ''}</span></div>{run.events?.length ? <ol className="grid gap-2 sm:grid-cols-2">{Array.from(new Map(run.events.map((event) => [event.stage, event])).values()).map((event) => <li key={event.stage} className="flex items-center gap-2 rounded-lg border border-navy/10 p-2 text-xs text-navy/65"><CheckCircle2 className="h-3.5 w-3.5 text-teal" />{STAGE_LABELS[event.stage] ?? event.stage}{event.duration_ms ? ` · ${(event.duration_ms / 1000).toFixed(1)} s` : ''}</li>)}</ol> : null}<div className="grid gap-3 sm:grid-cols-2">{run.artifacts?.map((artifact) => <Button key={artifact.kind} variant="ghost" onClick={() => download(artifact.kind)}><Download className="h-4 w-4" />{ARTIFACT_LABELS[artifact.kind] ?? `Descargar ${artifact.kind}`}</Button>)}</div><Button disabled={!canActivateResult(run.status, Boolean(run.artifacts?.some((artifact) => artifact.kind === 'annual')))} onClick={() => void perform(async () => { await activateRun(run.id, `${name} — resultado`); setNotice('La base quedó disponible para usar en la plataforma.') })}><FilePlus2 className="h-4 w-4" />Usar esta base en la plataforma</Button></div> : null}</div> : null}
    </Card>
  </div>
}
