import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Download,
  FileCog, Loader2, Play, ShieldCheck,
} from 'lucide-react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import PageHeader from '../components/ui/PageHeader'
import { ApiError } from '../lib/api'
import {
  activateRun, createProject, enqueuePreview, enqueueRun, getExport, getRun,
  listDatasets, saveSources, validateProject,
} from './api'
import { useConsolidation } from './ConsolidationContext'
import type { DatasetOption, SourceRole } from './types'
import { canActivateResult, TERMINAL_RUN_STATUSES, upsertSource } from './state'

const STEPS = ['Proyecto', 'Fuentes', 'Validación', 'Relaciones', 'Recodificación', 'Previsualización', 'Control de calidad', 'Exportación']
const ROLES: Array<{ role: SourceRole; label: string; required: boolean }> = [
  { role: 'matricula', label: 'Matrícula (ancla)', required: true },
  { role: 'archivo_b', label: 'Archivo B', required: false },
  { role: 'archivo_c', label: 'Archivo C', required: false },
  { role: 'archivo_d', label: 'Archivo D', required: false },
  { role: 'oferta', label: 'Oferta académica', required: false },
  { role: 'historica', label: 'Base histórica', required: false },
  { role: 'codebook_matricula', label: 'Libro Matrícula', required: false },
  { role: 'codebook_b', label: 'Libro B', required: false },
  { role: 'codebook_c', label: 'Libro C', required: false },
  { role: 'codebook_d', label: 'Libro D', required: false },
]

function statusBadge(status: string) {
  if (status === 'certified') return <Badge tone="green">Certificado</Badge>
  if (status === 'partial' || status === 'valid_with_warnings') return <Badge tone="gold">Parcial / advertencias</Badge>
  if (status === 'blocked' || status === 'failed') return <Badge tone="coral">Bloqueado</Badge>
  return <Badge tone="teal">{status}</Badge>
}

export default function ConsolidationWizard() {
  const { project, setProject, sources, setSources, validation, setValidation, run, setRun } = useConsolidation()
  const [step, setStep] = useState(0)
  const [name, setName] = useState('Consolidación admisión 2026')
  const [includeHistorical, setIncludeHistorical] = useState(false)
  const [datasets, setDatasets] = useState<DatasetOption[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const selectedByRole = useMemo(() => new Map(sources.map((source) => [source.role, source.dataset_id])), [sources])

  useEffect(() => {
    void listDatasets().then(setDatasets).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : 'No se pudieron cargar los documentos.')
    })
  }, [])

  useEffect(() => {
    if (!run || TERMINAL_RUN_STATUSES.has(run.status)) return
    const timer = window.setInterval(() => {
      void getRun(run.id).then(setRun).catch(() => undefined)
    }, 2500)
    return () => window.clearInterval(timer)
  }, [run, setRun])

  const perform = async (action: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (reason) {
      setError(reason instanceof ApiError || reason instanceof Error ? reason.message : 'No se pudo completar la acción.')
    } finally {
      setBusy(false)
    }
  }

  const chooseSource = (role: SourceRole, datasetId: string, required: boolean) => {
    setSources(upsertSource(sources, role, datasetId, required))
    setValidation(null)
  }

  const download = async (kind: string) => {
    if (!run) return
    await perform(async () => {
      const result = await getExport(run.id, kind)
      if (result.url) window.location.assign(result.url)
      else if (result.local_path) setError(`Artefacto local: ${result.local_path}`)
    })
  }

  return (
    <div>
      <PageHeader title="Consolidar y recodificar bases" subtitle="Relaciona varias fuentes sin multiplicar registros, con trazabilidad y controles auditables." />
      <ol className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8" aria-label="Pasos de consolidación">
        {STEPS.map((label, index) => (
          <li key={label}>
            <button type="button" onClick={() => setStep(index)} className={`min-h-16 w-full rounded-lg border px-2 py-2 text-left text-xs font-semibold ${step === index ? 'border-teal bg-teal/10 text-navy' : 'border-navy/10 bg-white text-navy/60'}`}>
              <span className="block text-[10px] text-teal">{index + 1}</span>{label}
            </button>
          </li>
        ))}
      </ol>

      {error ? <div role="alert" className="mb-4 flex items-start gap-2 rounded-lg border border-coral/30 bg-coral/10 p-3 text-sm text-coral"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div> : null}

      <Card className="min-h-80">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div><p className="text-xs font-semibold uppercase tracking-wide text-teal">Paso {step + 1}</p><h2 className="text-lg font-semibold text-navy">{STEPS[step]}</h2></div>
          {project ? <Badge tone="navy">Proyecto creado</Badge> : null}
        </div>

        {step === 0 ? (
          <div className="max-w-xl space-y-4">
            <label className="block text-sm font-semibold text-navy">Nombre del proyecto<input value={name} onChange={(event) => setName(event.target.value)} className="mt-1 w-full rounded-lg border border-navy/20 px-3 py-2 font-normal" /></label>
            <label className="flex items-start gap-2 text-sm text-navy/75"><input type="checkbox" checked={includeHistorical} onChange={(event) => setIncludeHistorical(event.target.checked)} className="mt-1 accent-teal" /><span><strong className="block text-navy">Intentar consolidación histórica</strong>Si el esquema no coincide, se conservará la base anual y se informará la advertencia.</span></label>
            <Button disabled={busy || !name.trim()} onClick={() => void perform(async () => { const created = await createProject(name.trim(), includeHistorical); setProject(created); setStep(1) })}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileCog className="h-4 w-4" />}Crear proyecto</Button>
          </div>
        ) : null}

        {step === 1 ? (
          <div className="space-y-3">
            <p className="text-sm text-navy/65">Selecciona documentos ya cargados. El backend comprueba que todos pertenezcan a tu cuenta.</p>
            <div className="grid gap-3 md:grid-cols-2">
              {ROLES.map(({ role, label, required }) => (
                <label key={role} className="block rounded-lg border border-navy/10 p-3 text-sm font-semibold text-navy">{label}{required ? <span className="ml-1 text-coral">*</span> : null}
                  <select value={selectedByRole.get(role) ?? ''} onChange={(event) => chooseSource(role, event.target.value, required)} className="mt-1 w-full rounded-lg border border-navy/20 bg-white px-2 py-2 font-normal">
                    <option value="">No asignado</option>{datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}
                  </select>
                </label>
              ))}
            </div>
            <Button disabled={busy || !project || !selectedByRole.has('matricula')} onClick={() => void perform(async () => { if (!project) return; setProject(await saveSources(project.id, sources)); setStep(2) })}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}Guardar fuentes</Button>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="space-y-4"><p className="text-sm text-navy/65">La validación revisa fuentes obligatorias, ownership y plantilla objetivo.</p><Button disabled={busy || !project} onClick={() => void perform(async () => { if (!project) return; setValidation(await validateProject(project.id)) })}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}Validar configuración</Button>{validation ? <div className="rounded-lg border border-navy/10 p-4">{statusBadge(validation.status)}<p className="mt-2 text-sm text-navy/70">{validation.source_count} fuentes · {validation.target_columns} columnas objetivo</p>{validation.warnings.map((warning) => <p key={warning} className="mt-1 text-sm text-gold">Advertencia: {warning}</p>)}{validation.blocking.map((issue) => <p key={issue} className="mt-1 text-sm text-coral">Bloqueo: {issue}</p>)}</div> : null}</div>
        ) : null}

        {step === 3 ? <div className="grid gap-4 md:grid-cols-3"><Card className="bg-teal/[0.04]"><h3 className="font-semibold">Matrícula</h3><p className="mt-1 text-sm text-navy/60">Define el universo final: nunca se eliminan ni multiplican filas.</p></Card><Card><h3 className="font-semibold">Archivo D</h3><p className="mt-1 text-sm text-navy/60">Se reduce por ID, carrera y estado seleccionado antes de relacionarlo.</p></Card><Card><h3 className="font-semibold">Oferta</h3><p className="mt-1 text-sm text-navy/60">Solo enriquece coincidencias únicas o resueltas por vigencia declarada.</p></Card></div> : null}

        {step === 4 ? <div className="space-y-3 text-sm text-navy/70"><p><strong className="text-navy">Aliases auditados:</strong> ID_RBD ↔ RBD dentro del manifiesto del proyecto.</p><p><strong className="text-navy">Precedencia:</strong> B para demografía; C para clasificación y puntajes disponibles.</p><p><strong className="text-navy">Desconocidos:</strong> permanecen vacíos y se contabilizan como <code>unmapped</code>.</p></div> : null}

        {step === 5 ? <div className="space-y-4"><p className="text-sm text-navy/65">El dry-run se ejecuta en el worker; la muestra nunca carga miles de filas en el navegador.</p><Button disabled={busy || !project || validation?.status === 'blocked'} onClick={() => void perform(async () => { if (project) setRun(await enqueuePreview(project.id)) })}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}Preparar previsualización</Button>{run ? <div className="flex items-center gap-2">{statusBadge(run.status)}{TERMINAL_RUN_STATUSES.has(run.status) ? null : <Loader2 className="h-4 w-4 animate-spin text-teal" />}</div> : null}</div> : null}

        {step === 6 ? <div className="space-y-4">{run?.report ? <><div className="grid gap-3 sm:grid-cols-3"><Card><p className="text-xs text-navy/50">Filas anuales</p><p className="text-xl font-semibold">{run.report.row_counts?.annual ?? '—'}</p></Card><Card><p className="text-xs text-navy/50">ID únicos</p><p className="text-xl font-semibold">{run.report.row_counts?.unique_ids ?? '—'}</p></Card><Card><p className="text-xs text-navy/50">Tiempo</p><p className="text-xl font-semibold">{run.report.timings_ms?.total ? `${Math.round(run.report.timings_ms.total / 1000)} s` : '—'}</p></Card></div><ul className="space-y-2">{run.report.issues?.map((issue) => <li key={issue.code} className="rounded-lg border border-navy/10 p-3 text-sm">{statusBadge(issue.severity)} <span className="ml-2 text-navy/70">{issue.message}{issue.count ? ` (${issue.count})` : ''}</span></li>)}</ul></> : <p className="text-sm text-navy/60">Ejecuta una previsualización para ver los controles de calidad.</p>}</div> : null}

        {step === 7 ? <div className="space-y-4"><Button disabled={busy || !project} onClick={() => void perform(async () => { if (project) setRun(await enqueueRun(project.id)) })}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}Generar artefactos</Button>{run && TERMINAL_RUN_STATUSES.has(run.status) ? <div className="space-y-3"><div>{statusBadge(run.status)}</div><div className="flex flex-wrap gap-2">{run.artifacts?.map((artifact) => <Button key={artifact.kind} variant="ghost" onClick={() => void download(artifact.kind)}><Download className="h-4 w-4" />{artifact.kind}</Button>)}</div><Button disabled={!canActivateResult(run.status, Boolean(run.artifacts?.some((item) => item.kind === 'annual')))} onClick={() => void perform(async () => { await activateRun(run.id, `${name} — resultado`); setError('Resultado registrado como dataset derivado.') })}>Usar resultado en la plataforma</Button></div> : null}</div> : null}
      </Card>

      <div className="mt-4 flex justify-between gap-3"><Button variant="ghost" disabled={step === 0} onClick={() => setStep((value) => Math.max(0, value - 1))}><ChevronLeft className="h-4 w-4" />Anterior</Button><Button variant="ghost" disabled={step === STEPS.length - 1} onClick={() => setStep((value) => Math.min(STEPS.length - 1, value + 1))}>Siguiente<ChevronRight className="h-4 w-4" /></Button></div>
    </div>
  )
}
