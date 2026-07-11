import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  Coins,
  Columns3,
  Copy,
  Download,
  Eraser,
  FileSpreadsheet,
  FileWarning,
  Loader2,
  Rows3,
  Settings2,
  Sparkles,
  Type,
  Upload,
  Wand2,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import EmptyState from '../components/ui/EmptyState'
import Toggle from '../components/ui/Toggle'
import { PlanUpsell } from '../components/ui/PlanGate'
import { useDataset } from '../data/DatasetContext'
import { apiGet, apiPost, apiDownload, buildDatasetForm, ApiError } from '../lib/api'
import { saveCleaningJob, saveColumnMapping } from '../lib/datasets'
import { supabaseConfigured } from '../lib/supabase'
import { formatNumber } from '../lib/format'
import { useCapability } from '../lib/usePlan'
import {
  DEFAULT_RULES,
  type CleanResult,
  type CleaningRules,
  type DirectedInfo,
  type PlansUsage,
} from '../lib/types'

const RULE_LABELS: Array<{ key: keyof CleaningRules; label: string }> = [
  { key: 'fechas', label: 'Estándar de formato de fecha' },
  { key: 'textos', label: 'Unificar texto' },
  { key: 'duplicados', label: 'Eliminar duplicados' },
  { key: 'tipos', label: 'Convertir tipos de dato' },
  { key: 'nulos', label: 'Normalizar y señalizar nulos' },
  { key: 'columnas_vacias', label: 'Eliminar columnas vacías' },
  { key: 'fuera_de_rango', label: 'Validar rangos y outliers' },
]

const PROBLEM_LABELS: Array<{
  key: keyof CleanResult['problemas']
  label: string
  icon: typeof Copy
}> = [
  { key: 'duplicados', label: 'Duplicados', icon: Copy },
  { key: 'valores_nulos', label: 'Valores nulos', icon: FileWarning },
  { key: 'fechas_invalidas', label: 'Formatos de fecha inválidos', icon: CalendarClock },
  { key: 'textos_inconsistentes', label: 'Textos inconsistentes', icon: Type },
  { key: 'tipos_incorrectos', label: 'Tipos de datos incorrectos', icon: Settings2 },
  { key: 'columnas_vacias', label: 'Columnas vacías', icon: Columns3 },
  { key: 'valores_fuera_de_rango', label: 'Valores fuera de rango', icon: AlertTriangle },
]

/** Roles del negocio corregibles desde la UI (Fase 7 §5.10). */
const MAPPING_ROLES: Array<{ role: string; label: string }> = [
  { role: 'fecha', label: 'Fecha' },
  { role: 'monto', label: 'Monto / Ventas' },
  { role: 'costo', label: 'Costo' },
  { role: 'cantidad', label: 'Cantidad' },
  { role: 'producto', label: 'Producto' },
  { role: 'categoria', label: 'Categoría' },
  { role: 'cliente', label: 'Cliente' },
  { role: 'canal', label: 'Canal' },
  { role: 'sucursal', label: 'Sucursal' },
  { role: 'vendedor', label: 'Vendedor' },
]

function qualityLabel(quality: number): { text: string; tone: 'green' | 'gold' | 'coral' } {
  if (quality >= 90) return { text: 'Excelente', tone: 'green' }
  if (quality >= 75) return { text: 'Buena', tone: 'green' }
  if (quality >= 50) return { text: 'Regular', tone: 'gold' }
  return { text: 'Baja', tone: 'coral' }
}

function QualityRing({ quality }: { quality: number }) {
  const radius = 26
  const circumference = 2 * Math.PI * radius
  const filled = (quality / 100) * circumference
  const color = quality >= 75 ? 'var(--color-green)' : quality >= 50 ? 'var(--color-gold)' : 'var(--color-coral)'
  return (
    <div className="relative h-16 w-16">
      <svg viewBox="0 0 64 64" className="h-16 w-16 -rotate-90">
        <circle cx="32" cy="32" r={radius} fill="none" stroke="#e8edf0" strokeWidth="7" />
        <circle
          cx="32"
          cy="32"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference - filled}`}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-navy">
        {Math.round(quality)}%
      </span>
    </div>
  )
}

export default function Limpieza() {
  const {
    file,
    datasetId,
    storagePath,
    standardization,
    cleaning,
    setCleaning,
    mappingOverride,
    setMappingOverride,
    sheet,
  } = useDataset()
  const [detection, setDetection] = useState<CleanResult | null>(null)
  const [rules, setRules] = useState<CleaningRules>(DEFAULT_RULES)
  const [detecting, setDetecting] = useState(false)
  const [applying, setApplying] = useState(false)
  const [downloading, setDownloading] = useState<'xlsx' | 'csv' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [persistWarning, setPersistWarning] = useState<string | null>(null)
  const detectStartedFor = useRef<File | null>(null)

  // ── Limpieza dirigida (Analista/Gold) y descarga de base limpia (Analista+) ──
  const aiCleaning = useCapability('ai_cleaning')
  const downloadClean = useCapability('download_clean_dataset')
  const [instructions, setInstructions] = useState('')
  const [assistedRunning, setAssistedRunning] = useState(false)
  const [assistedError, setAssistedError] = useState<string | null>(null)
  const [directed, setDirected] = useState<DirectedInfo | null>(null)
  const [usage, setUsage] = useState<PlansUsage | null>(null)

  const refreshUsage = () => {
    apiGet<PlansUsage>('/plans/usage')
      .then(setUsage)
      .catch(() => setUsage(null))
  }

  useEffect(() => {
    refreshUsage()
  }, [])

  useEffect(() => {
    if (!file || cleaning || detectStartedFor.current === file) return
    detectStartedFor.current = file
    setDetecting(true)
    setError(null)
    apiPost<CleanResult>('/clean', buildDatasetForm(file, storagePath, { apply: 'false', ...(sheet ? { sheet } : {}) }))
      .then(setDetection)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'No se pudo analizar el archivo.'),
      )
      .finally(() => setDetecting(false))
  }, [file, storagePath, cleaning, sheet])

  if (!file || !standardization) {
    return (
      <>
        <PageHeader
          title="Limpieza de datos ✨"
          subtitle="Revisa, ajusta y limpia tus datos para que estén listos para el análisis."
        />
        <EmptyState
          icon={Sparkles}
          title="No hay archivos para limpiar"
          description="Primero estandariza un archivo. Después podrás revisar los problemas detectados (duplicados, nulos, formatos inválidos) y aplicar la limpieza."
          ctaLabel="Ir a Estandarización"
          ctaTo="/estandarizacion"
        />
      </>
    )
  }

  const result = cleaning ?? detection
  const applied = cleaning !== null
  const totalProblems = result
    ? PROBLEM_LABELS.reduce((sum, { key }) => sum + (result.problemas[key] ?? 0), 0)
    : 0
  const quality = result
    ? applied
      ? result.resumen.calidad_despues
      : result.resumen.calidad_antes
    : null

  const effectiveMapping: Record<string, string> = {
    ...(result?.mapeo ?? standardization.mapeo),
    ...(mappingOverride ?? {}),
  }
  const availableColumns = result?.preview.columnas ?? standardization.preview.columnas

  const mappingFields = (): Record<string, string> => ({
    ...(mappingOverride ? { mapping: JSON.stringify(mappingOverride) } : {}),
    ...(sheet ? { sheet } : {}),
  })

  // Qué se corregirá según los toggles activos (mismo cálculo que hace la API).
  const planned = result
    ? [
        { label: 'Filas duplicadas a eliminar', value: rules.duplicados ? result.problemas.duplicados : 0 },
        { label: 'Valores nulos normalizados y señalizados', value: rules.nulos ? result.problemas.valores_nulos : 0 },
        {
          label: 'Fechas a estandarizar',
          value:
            result.estandarizacion.fechas_estandarizadas +
            (rules.fechas ? result.problemas.fechas_invalidas : 0),
        },
        { label: 'Textos a unificar', value: rules.textos ? result.problemas.textos_inconsistentes : 0 },
        { label: 'Tipos de datos a corregir', value: rules.tipos ? result.problemas.tipos_incorrectos : 0 },
        { label: 'Columnas vacías a eliminar', value: rules.columnas_vacias ? result.problemas.columnas_vacias : 0 },
        { label: 'Valores fuera de rango a revisar', value: rules.fuera_de_rango ? result.problemas.valores_fuera_de_rango : 0 },
      ]
    : []

  const issueMap = new Map<string, string>()
  if (result && !applied) {
    for (const issue of result.preview.issues) {
      issueMap.set(`${issue.fila}:${issue.columna}`, issue.tipo)
    }
  }

  const handleMappingChange = (role: string, column: string) => {
    const next: Record<string, string> = { ...effectiveMapping }
    if (column) {
      // Un mismo nombre de columna no puede cumplir dos roles.
      for (const [otherRole, otherCol] of Object.entries(next)) {
        if (otherCol === column && otherRole !== role) delete next[otherRole]
      }
      next[role] = column
    } else {
      delete next[role]
    }
    setMappingOverride(next)
    void saveColumnMapping(datasetId, next) // best-effort (migración 0008)
  }

  const handleDownload = async (fmt: 'xlsx' | 'csv') => {
    if (!file) return
    setDownloading(fmt)
    setError(null)
    try {
      const stem = file.name.replace(/\.[^.]+$/, '')
      const extra: Record<string, string> = {
        rules: JSON.stringify(rules),
        fmt,
        ...mappingFields(),
      }
      if (directed) {
        extra.scope = JSON.stringify({
          incluir: directed.columnas_incluir,
          excluir: directed.columnas_excluir,
        })
      }
      await apiDownload('/clean/download', buildDatasetForm(file, storagePath, extra), `${stem}_limpio.${fmt}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo descargar el archivo.')
    } finally {
      setDownloading(null)
    }
  }

  const finishApply = async (response: CleanResult) => {
    setCleaning(response)
    // Best-effort: si falla el guardado, la limpieza IGUAL quedó aplicada —
    // jamás mostrarlo como error de limpieza (solo aviso de historial).
    const saved = await saveCleaningJob(datasetId, rules, response)
    if (!saved && supabaseConfigured && datasetId) {
      setPersistWarning(
        'La limpieza se aplicó correctamente, pero no se pudo guardar en el historial.',
      )
    }
  }

  /** Botón principal: reglas por defecto, para TODOS los planes. */
  const handleApply = async () => {
    setApplying(true)
    setError(null)
    setPersistWarning(null)
    setDirected(null)
    try {
      const response = await apiPost<CleanResult>(
        '/clean',
        buildDatasetForm(file, storagePath, {
          apply: 'true',
          rules: JSON.stringify(rules),
          ...mappingFields(),
        }),
      )
      await finishApply(response)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo aplicar la limpieza.')
    } finally {
      setApplying(false)
    }
  }

  /** Botón del chat: limpieza dirigida con las variables escritas. */
  const handleAssisted = async () => {
    if (!instructions.trim()) {
      setAssistedError('Escribe qué variables o columnas quieres limpiar.')
      return
    }
    setAssistedRunning(true)
    setAssistedError(null)
    setPersistWarning(null)
    try {
      const response = await apiPost<CleanResult>(
        '/clean/assisted',
        buildDatasetForm(file, storagePath, {
          instructions: instructions.trim(),
          rules: JSON.stringify(rules),
          ...mappingFields(),
        }),
      )
      setDirected(response.dirigida ?? null)
      await finishApply(response)
      refreshUsage()
    } catch (err) {
      setAssistedError(
        err instanceof ApiError ? err.message : 'No se pudo ejecutar la limpieza dirigida.',
      )
    } finally {
      setAssistedRunning(false)
    }
  }

  const limpiezaUsage = usage?.disponible ? usage.limpieza : null
  const baseRestantes = limpiezaUsage
    ? Math.max(limpiezaUsage.base - limpiezaUsage.usadas_mes, 0)
    : null
  const totalRestantes =
    limpiezaUsage && baseRestantes !== null ? baseRestantes + limpiezaUsage.addons : null
  const sinIntentos = totalRestantes !== null && totalRestantes <= 0
  const assistedLocked = aiCleaning.enforced && !aiCleaning.loading && !aiCleaning.hasByPlan
  const downloadLocked = downloadClean.enforced && !downloadClean.loading && !downloadClean.hasByPlan

  const steps = [
    { title: 'Cargar datos', text: 'Archivo cargado', done: true, warn: false },
    {
      title: 'Revisar problemas',
      text: result ? `${formatNumber(totalProblems)} detectados` : 'Analizando…',
      done: result !== null,
      warn: result !== null && totalProblems > 0 && !applied,
    },
    { title: 'Configurar reglas', text: 'Reglas automáticas activas', done: true, warn: false },
    { title: 'Aplicar limpieza', text: applied ? 'Limpieza aplicada' : 'Aún no ejecutado', done: applied, warn: false },
    { title: 'Dataset limpio', text: applied ? 'Listo para el análisis' : 'Pendiente', done: applied, warn: false },
  ]

  return (
    <>
      <div className="flex items-start justify-between gap-4">
        <PageHeader
          title="Limpieza de datos ✨"
          subtitle="Revisa, ajusta y limpia tus datos para que estén listos para el análisis."
        />
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {/* Fase 11 §6.2: salida explícita para estandarizar OTRO documento */}
          <Link
            to="/estandarizacion"
            className="inline-flex items-center gap-2 rounded-lg border border-navy/20 bg-white px-4 py-2.5 text-sm font-medium text-navy transition-colors hover:bg-navy/5"
          >
            <Upload className="h-4 w-4" /> Procesar otro archivo
          </Link>
          <Link
            to="/historial"
            className="inline-flex items-center gap-2 rounded-lg border border-navy/20 bg-white px-4 py-2.5 text-sm font-medium text-navy transition-colors hover:bg-navy/5"
          >
            <CalendarClock className="h-4 w-4" /> Historial de cargas
          </Link>
        </div>
      </div>

      {/* Encabezado: archivo, filas, columnas, calidad, estado (tonos suaves) */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Card className="!p-4 bg-gradient-to-br from-green/[0.06] to-transparent">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-green/10">
              <FileSpreadsheet className="h-5 w-5 text-green" />
            </div>
            <div className="min-w-0">
              <p className="text-xs text-navy/50">Archivo actual</p>
              <p className="truncate text-sm font-semibold text-navy" title={file.name}>
                {file.name}
              </p>
              <Link to="/estandarizacion" className="text-xs font-medium text-teal hover:underline">
                Cambiar archivo
              </Link>
            </div>
          </div>
        </Card>
        <Card className="!p-4 bg-gradient-to-br from-teal/[0.06] to-transparent">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-teal/10">
              <Rows3 className="h-5 w-5 text-teal" />
            </div>
            <div>
              <p className="text-xs text-navy/50">Filas</p>
              <p className="text-xl font-bold text-navy">
                {formatNumber(applied && result ? result.resumen.filas_despues : standardization.filas)}
              </p>
              <p className="text-xs text-navy/50">Registros totales</p>
            </div>
          </div>
        </Card>
        <Card className="!p-4 bg-gradient-to-br from-navy/[0.05] to-transparent">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-navy/10">
              <Columns3 className="h-5 w-5 text-navy/70" />
            </div>
            <div>
              <p className="text-xs text-navy/50">Columnas</p>
              <p className="text-xl font-bold text-navy">
                {formatNumber(applied && result ? result.resumen.columnas_despues : standardization.columnas)}
              </p>
              <p className="text-xs text-navy/50">Variables detectadas</p>
            </div>
          </div>
        </Card>
        <Card className="!p-4 bg-gradient-to-br from-gold/[0.08] to-transparent">
          <div className="flex items-center gap-3">
            {quality !== null ? <QualityRing quality={quality} /> : <Loader2 className="h-8 w-8 animate-spin text-teal" />}
            <div>
              <p className="text-xs text-navy/50">Calidad del dato</p>
              {quality !== null && (
                <Badge tone={qualityLabel(quality).tone}>{qualityLabel(quality).text}</Badge>
              )}
            </div>
          </div>
        </Card>
        <Card className={`!p-4 bg-gradient-to-br ${applied ? 'from-green/[0.08]' : 'from-gold/[0.08]'} to-transparent`}>
          <div className="flex items-start gap-3">
            <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${applied ? 'bg-green/10' : 'bg-gold/15'}`}>
              <CheckCircle2 className={`h-5 w-5 ${applied ? 'text-green' : 'text-gold'}`} />
            </div>
            <div>
              <p className="text-xs text-navy/50">Estado</p>
              <p className="text-sm font-semibold text-navy">
                {applied ? 'Dataset limpio' : 'Listo para limpiar'}
              </p>
              <p className="text-xs text-navy/50">
                {applied
                  ? 'Limpieza aplicada correctamente.'
                  : 'Se detectaron problemas que puedes revisar.'}
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* Pasos de limpieza — barra horizontal compacta (Fase 8: sin columna
          lateral alargada; el ancho completo queda para los datos) */}
      <Card className="mt-6 !p-4">
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {steps.map((step, index) => (
            <li key={step.title} className="flex items-center gap-2.5">
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                  step.done
                    ? 'bg-green/15 text-green'
                    : step.warn
                      ? 'bg-gold/20 text-gold'
                      : 'bg-navy/10 text-navy/50'
                }`}
              >
                {step.done ? <CheckCircle2 className="h-4 w-4" /> : index + 1}
              </span>
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-navy">{step.title}</p>
                <p className="truncate text-[11px] text-navy/55">{step.text}</p>
              </div>
              {index < steps.length - 1 && (
                <span className="ml-auto hidden text-navy/20 lg:block">›</span>
              )}
            </li>
          ))}
        </ol>
      </Card>

      <div className="mt-6 space-y-6">
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-coral/40 bg-coral/10 px-4 py-3 text-sm text-coral">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <p>{error}</p>
          </div>
        )}
        {persistWarning && (
          <div className="flex items-start gap-2 rounded-lg border border-gold/40 bg-gold/10 px-4 py-3 text-sm text-navy/80">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
            <p>{persistWarning}</p>
          </div>
        )}

        {applied && result ? (
          <>
            <Card className="border-green/30 bg-gradient-to-br from-green/[0.07] to-transparent">
              <div className="flex items-start gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-green/15">
                  <CheckCircle2 className="h-6 w-6 text-green" />
                </div>
                <div className="flex-1">
                  <h2 className="text-base font-semibold text-navy">
                    {directed ? 'Limpieza dirigida aplicada ✅' : 'Limpieza aplicada ✅'}
                  </h2>
                  <p className="mt-1 text-sm text-navy/70">
                    Tu dataset quedó limpio y cargado para el resto de los módulos. La calidad
                    subió de <strong>{result.resumen.calidad_antes}%</strong> a{' '}
                    <strong>{result.resumen.calidad_despues}%</strong>. Filas:{' '}
                    {formatNumber(result.resumen.filas_antes)} →{' '}
                    {formatNumber(result.resumen.filas_despues)} · Columnas:{' '}
                    {formatNumber(result.resumen.columnas_antes)} →{' '}
                    {formatNumber(result.resumen.columnas_despues)}.
                  </p>
                  {directed && directed.columnas_incluir.length > 0 && (
                    <p className="mt-2 text-sm text-navy/70">
                      <Wand2 className="mr-1 inline h-4 w-4 text-teal" />
                      Reglas por columna aplicadas a:{' '}
                      <strong>{directed.columnas_incluir.join(', ')}</strong>
                      {directed.columnas_excluir.length > 0 && (
                        <> · sin tocar: {directed.columnas_excluir.join(', ')}</>
                      )}
                    </p>
                  )}
                </div>
              </div>
            </Card>

            {/* Descarga con protagonismo propio (Fase 8) */}
            <Card className="border-teal/25 bg-gradient-to-r from-teal/[0.06] via-transparent to-transparent">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-teal/10">
                    <Download className="h-5.5 w-5.5 text-teal" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-navy">Tu base actualizada</h3>
                    <p className="text-xs text-navy/55">
                      Excel con los datos intactos + hoja de Observaciones; celdas marcadas:
                      amarillo = fecha a revisar, rojo = dato faltante.
                    </p>
                  </div>
                </div>
                {downloadLocked ? (
                  <div className="min-w-0 flex-1 sm:max-w-md">
                    <PlanUpsell planNeeded="Analista" feature="descargar tu base limpia" compact />
                  </div>
                ) : (
                  <div className="flex items-center gap-2.5">
                    <button
                      onClick={() => void handleDownload('xlsx')}
                      disabled={downloading !== null}
                      className="inline-flex items-center gap-2 rounded-lg bg-teal px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-teal/90 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {downloading === 'xlsx' ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                      Descargar base actualizada
                    </button>
                    <button
                      onClick={() => void handleDownload('csv')}
                      disabled={downloading !== null}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-teal/40 px-3.5 py-2.5 text-xs font-semibold text-teal transition-colors hover:bg-teal/5 disabled:cursor-not-allowed disabled:opacity-50"
                      title="Descargar como CSV"
                    >
                      {downloading === 'csv' ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : null}
                      CSV
                    </button>
                    <Link
                      to="/explorar"
                      className="inline-flex items-center gap-2 rounded-lg bg-navy px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-navy-deep"
                    >
                      Continuar <ArrowRight className="h-4 w-4" />
                    </Link>
                  </div>
                )}
              </div>
            </Card>

            {result.avisos && result.avisos.length > 0 && (
              <Card className="!p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-navy/50">
                  Avisos del motor
                </p>
                <ul className="mt-2 space-y-1.5">
                  {result.avisos.map((aviso) => (
                    <li key={aviso} className="flex items-start gap-2 text-xs text-navy/65">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gold" />
                      {aviso}
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </>
        ) : (
          <>
            {/* Vista previa con errores resaltados — ancho completo */}
            <Card>
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-base font-semibold text-navy">
                  Vista previa de los datos originales
                </h2>
                <Badge tone="gold">Antes de la limpieza</Badge>
              </div>
              {detecting || !result ? (
                <div className="flex items-center gap-3 py-10 text-sm text-navy/60">
                  <Loader2 className="h-5 w-5 animate-spin text-teal" />
                  Analizando problemas del archivo...
                </div>
              ) : (
                <>
                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-navy/10 text-left font-semibold text-navy/60">
                          <th className="py-2 pr-3">#</th>
                          {result.preview.columnas.map((col) => (
                            <th key={col} className="py-2 pr-4 whitespace-nowrap">
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {result.preview.filas.map((row, rowIndex) => {
                          const isDuplicate = issueMap.get(`${rowIndex}:*`) === 'duplicado'
                          return (
                            <tr
                              key={rowIndex}
                              className={`border-b border-navy/5 ${isDuplicate ? 'bg-coral/5' : ''}`}
                            >
                              <td className="py-2 pr-3 text-navy/40">{rowIndex + 1}</td>
                              {row.map((cell, colIndex) => {
                                const column = result.preview.columnas[colIndex]
                                const issue = issueMap.get(`${rowIndex}:${column}`)
                                return (
                                  <td
                                    key={colIndex}
                                    className={`py-2 pr-4 whitespace-nowrap ${
                                      issue
                                        ? 'font-semibold text-coral'
                                        : isDuplicate
                                          ? 'text-coral/80'
                                          : 'text-navy/75'
                                    }`}
                                    title={issue ? `Problema: ${issue.replace('_', ' ')}` : undefined}
                                  >
                                    {cell || '—'}
                                  </td>
                                )
                              })}
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                  <div className="mt-4 flex items-start gap-2 rounded-lg border border-gold/40 bg-gold/10 px-4 py-3 text-sm text-navy">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
                    <p>
                      Detectamos <strong>{formatNumber(totalProblems)} problemas</strong> en tus
                      datos que puedes revisar y corregir antes de continuar.
                    </p>
                  </div>
                  {result.avisos && result.avisos.length > 0 && (
                    <ul className="mt-3 space-y-1.5">
                      {result.avisos.map((aviso) => (
                        <li key={aviso} className="flex items-start gap-2 text-xs text-navy/60">
                          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gold" />
                          {aviso}
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </Card>

            {/* Problemas / correcciones / reglas — tres columnas a lo ancho */}
            {result && (
              <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
                <Card className="bg-gradient-to-br from-coral/[0.05] to-transparent">
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-coral/10">
                      <FileWarning className="h-4 w-4 text-coral" />
                    </div>
                    <h3 className="text-sm font-semibold text-navy">Problemas detectados</h3>
                  </div>
                  <ul className="mt-4 space-y-2.5">
                    {PROBLEM_LABELS.map(({ key, label, icon: Icon }) => (
                      <li key={key} className="flex items-center justify-between gap-2 text-sm">
                        <span className="flex items-center gap-2 text-navy/70">
                          <Icon className="h-4 w-4 text-navy/40" /> {label}
                        </span>
                        <span
                          className={`font-semibold ${
                            (result.problemas[key] ?? 0) > 0 ? 'text-coral' : 'text-navy/40'
                          }`}
                        >
                          {formatNumber(result.problemas[key] ?? 0)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Card>

                <Card className="bg-gradient-to-br from-teal/[0.05] to-transparent">
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-teal/10">
                      <Eraser className="h-4 w-4 text-teal" />
                    </div>
                    <h3 className="text-sm font-semibold text-navy">
                      Qué se eliminará / corregirá
                    </h3>
                  </div>
                  <ul className="mt-4 space-y-2.5">
                    {planned.map(({ label, value }) => (
                      <li key={label} className="flex items-center justify-between gap-2 text-sm">
                        <span className="text-navy/70">{label}</span>
                        <span className={`font-semibold ${value > 0 ? 'text-teal' : 'text-navy/40'}`}>
                          {formatNumber(value)}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-3 text-xs text-navy/45">
                    Los montos faltantes nunca se rellenan con 0: quedan señalizados para
                    no sesgar tus indicadores.
                  </p>
                </Card>

                <Card className="bg-gradient-to-br from-navy/[0.04] to-transparent md:col-span-2 xl:col-span-1">
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-navy/10">
                      <Settings2 className="h-4 w-4 text-navy/60" />
                    </div>
                    <h3 className="text-sm font-semibold text-navy">Reglas activas (automáticas)</h3>
                  </div>
                  <ul className="mt-4 space-y-3">
                    {RULE_LABELS.map(({ key, label }) => (
                      <li key={key} className="flex items-center justify-between gap-2 text-sm">
                        <span className="text-navy/70">{label}</span>
                        <Toggle
                          checked={rules[key]}
                          label={label}
                          onChange={(value) => setRules((prev) => ({ ...prev, [key]: value }))}
                        />
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>
            )}

            {/* Mapeo de columnas — a lo ancho, sin columna lateral (Fase 8) */}
            <Card>
              <div className="flex flex-wrap items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-teal/10">
                  <Settings2 className="h-4 w-4 text-teal" />
                </div>
                <h2 className="text-sm font-semibold text-navy">Mapeo de columnas</h2>
                <p className="text-xs text-navy/55">
                  · Revisa qué columna cumple cada rol del negocio: corregirlo mejora los
                  indicadores y la limpieza.
                </p>
              </div>
              <div className="mt-4 grid gap-x-6 gap-y-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                {MAPPING_ROLES.map(({ role, label }) => (
                  <label key={role} className="flex items-center justify-between gap-2 text-xs">
                    <span className="font-medium text-navy/70">{label}</span>
                    <select
                      value={effectiveMapping[role] ?? ''}
                      onChange={(e) => handleMappingChange(role, e.target.value)}
                      className="w-[140px] rounded-md border border-navy/20 bg-white px-2 py-1.5 text-xs text-navy outline-none focus:border-teal"
                    >
                      <option value="">Sin asignar</option>
                      {availableColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            </Card>
          </>
        )}

        {/* Barra de acción: botón "Limpiar datos" (todos los planes) */}
        {!applied && (
          <Card className="!p-4 bg-gradient-to-r from-teal/[0.04] to-transparent">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-navy/60">
                Limpieza con reglas por defecto, disponible en todos los planes.
              </p>
              <button
                onClick={() => void handleApply()}
                disabled={applying || assistedRunning || detecting || !result}
                className="inline-flex items-center gap-2 rounded-lg bg-teal px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-teal/90 disabled:cursor-not-allowed disabled:bg-teal/50"
              >
                {applying ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Limpiando...
                  </>
                ) : (
                  <>
                    Limpiar datos <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </div>
          </Card>
        )}

        {/* ── Chat de limpieza dirigida (Analista/Gold) ── */}
        {!applied && (
          <Card className="border-navy/15 !p-5 bg-gradient-to-br from-gold/[0.04] to-transparent">
            <div className="flex items-center gap-2">
              <Wand2 className="h-5 w-5 text-teal" />
              <h2 className="text-base font-semibold text-navy">
                Limpieza dirigida con tus variables
              </h2>
              <Badge tone="gold">Analista / Gold</Badge>
            </div>
            <p className="mt-1.5 text-sm text-navy/60">
              O escribe tú qué limpiar: menciona las columnas y reglas (ej:{' '}
              <em>"limpia Fecha y Ventas, elimina duplicados, no toques Cliente"</em>) y la
              plataforma dirige la limpieza con tus instrucciones.
            </p>

            {assistedLocked ? (
              <div className="mt-4">
                <PlanUpsell
                  planNeeded="Analista"
                  feature="dirigir la limpieza con tus propias variables"
                />
              </div>
            ) : (
              <>
                <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
                  <textarea
                    value={instructions}
                    onChange={(e) => {
                      setInstructions(e.target.value)
                      setAssistedError(null)
                    }}
                    disabled={assistedRunning || sinIntentos}
                    rows={2}
                    maxLength={2000}
                    placeholder="Escribe las variables o columnas que quieres limpiar…"
                    className="min-h-[3.25rem] flex-1 resize-y rounded-lg border border-navy/20 bg-white px-3.5 py-2.5 text-sm text-navy outline-none transition-colors placeholder:text-navy/35 focus:border-teal disabled:cursor-not-allowed disabled:bg-navy/5"
                  />
                  <button
                    onClick={() => void handleAssisted()}
                    disabled={
                      assistedRunning || applying || detecting || !result || sinIntentos || !instructions.trim()
                    }
                    className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-navy px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-navy-deep disabled:cursor-not-allowed disabled:bg-navy/40"
                  >
                    {assistedRunning ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" /> Limpiando...
                      </>
                    ) : (
                      <>
                        <Wand2 className="h-4 w-4" /> Limpiar con mis variables
                      </>
                    )}
                  </button>
                </div>

                {/* Advertencia de intentos (Fase 8: cupo por plan) */}
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                  <p className="flex items-start gap-1.5 text-xs text-navy/55">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gold" />
                    <span>
                      Tienes <strong>{limpiezaUsage ? limpiezaUsage.base : 10} intentos al mes</strong>
                      {limpiezaUsage && (
                        <>
                          {' '}
                          (quedan {baseRestantes}
                          {limpiezaUsage.addons > 0 && ` + ${limpiezaUsage.addons} tokens`})
                        </>
                      )}
                      . Sé claro y específico con las columnas y reglas. Para más intentos,{' '}
                      <Link to="/planes" className="font-semibold text-teal hover:underline">
                        agrega tokens en Planes
                      </Link>
                      .
                    </span>
                  </p>
                  {sinIntentos && (
                    <Link
                      to="/planes"
                      className="inline-flex items-center gap-1.5 rounded-lg bg-gold px-3.5 py-1.5 text-xs font-semibold text-navy-deep transition-colors hover:bg-gold/90"
                    >
                      <Coins className="h-3.5 w-3.5" /> Agregar tokens
                    </Link>
                  )}
                </div>

                {assistedError && (
                  <p className="mt-3 rounded-lg border border-coral/40 bg-coral/5 px-4 py-2.5 text-sm text-coral">
                    {assistedError}
                  </p>
                )}
              </>
            )}
          </Card>
        )}
      </div>
    </>
  )
}
