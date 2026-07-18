import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
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
  ShieldAlert,
  Sparkles,
  Trash2,
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
import { useDemo } from '../demo/DemoContext'
import { DemoEmptyActions } from '../demo/DemoBanner'
import { apiGet, apiPost, apiDownload, buildDatasetForm, ApiError } from '../lib/api'
import { saveCleaningJob, saveColumnMapping } from '../lib/datasets'
import { supabaseConfigured } from '../lib/supabase'
import { formatNumber } from '../lib/format'
import { useCapability, usePlan } from '../lib/usePlan'
import {
  basicMappingQuestions,
  cleaningScopeState,
  serializedAnalysisScope,
  updateBatchSheetErrors,
} from '../lib/multiSheet'
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
  { key: 'tipos', label: 'Convertir tipos de dato' },
  { key: 'nulos', label: 'Normalizar y señalizar nulos' },
  { key: 'columnas_vacias', label: 'Eliminar columnas vacías' },
  { key: 'fuera_de_rango', label: 'Validar rangos y outliers' },
]

const PROBLEM_LABELS: Array<{
  key: keyof CleanResult['problemas']
  label: string
  unit: string
  icon: typeof Copy
}> = [
  { key: 'duplicados', label: 'Filas idénticas repetidas', unit: 'filas', icon: Copy },
  { key: 'duplicados_probables', label: 'Coincidencias tras normalización', unit: 'filas', icon: Copy },
  { key: 'valores_nulos', label: 'Celdas físicamente vacías', unit: 'celdas', icon: FileWarning },
  { key: 'nulos_semanticos', label: 'Placeholders según el rol', unit: 'celdas', icon: FileWarning },
  { key: 'posibles_nulos_estructurales', label: 'Posibles patrones estructurales', unit: 'patrones', icon: FileWarning },
  { key: 'fechas_invalidas', label: 'Fechas que requieren revisión', unit: 'celdas', icon: CalendarClock },
  { key: 'textos_inconsistentes', label: 'Textos que cambiarían', unit: 'celdas', icon: Type },
  { key: 'tipos_incorrectos', label: 'Tipos incompatibles', unit: 'celdas', icon: Settings2 },
  { key: 'columnas_vacias', label: 'Columnas completamente vacías', unit: 'columnas', icon: Columns3 },
  { key: 'montos_cero', label: 'Montos en cero para revisión', unit: 'celdas', icon: Coins },
  { key: 'montos_negativos', label: 'Montos negativos para revisión', unit: 'celdas', icon: Coins },
  { key: 'outliers_iqr', label: 'Posibles valores atípicos estadísticos (IQR)', unit: 'observaciones', icon: AlertTriangle },
]

const MAPPING_ROLES: Array<{ role: string; label: string; description: string }> = [
  { role: 'fecha', label: 'Fecha', description: 'La fecha en que ocurrió cada venta o movimiento.' },
  { role: 'monto', label: 'Monto / Ventas', description: 'La columna con el valor de cada venta.' },
  { role: 'costo', label: 'Costo', description: 'El costo asociado a cada venta o producto.' },
  { role: 'cantidad', label: 'Cantidad', description: 'Las unidades incluidas en cada registro.' },
  { role: 'producto', label: 'Producto', description: 'El producto o servicio vendido.' },
  { role: 'categoria', label: 'Categoría', description: 'La agrupación comercial del producto o servicio.' },
  { role: 'cliente', label: 'Cliente', description: 'La persona o empresa asociada al registro.' },
  { role: 'canal', label: 'Canal', description: 'El medio por el que se realizó la venta.' },
  { role: 'sucursal', label: 'Sucursal', description: 'La tienda, sede o local de origen.' },
  { role: 'vendedor', label: 'Vendedor', description: 'La persona responsable de la venta.' },
]

const IMPORTANT_MAPPING_ROLES = new Set(['monto', 'fecha', 'costo', 'producto', 'categoria'])
const MEDIUM_ROLE_CONFIDENCE = 0.75
const RESTORE_STATE_TIMEOUT_MS = 15_000

function applyMappingOverrides(
  automatic: Record<string, string>,
  override: Record<string, string> | null,
): Record<string, string> {
  const resolved = { ...automatic }
  for (const [role, column] of Object.entries(override ?? {})) {
    if (column) resolved[role] = column
    else delete resolved[role]
  }
  return resolved
}

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
        {formatNumber(quality)}%
      </span>
    </div>
  )
}

export default function Limpieza() {
  const location = useLocation()
  const demo = useDemo()
  const {
    file,
    datasetId,
    storagePath,
    uploadedAt,
    standardization,
    cleaning,
    setCleaning,
    mappingOverride,
    setMappingOverride,
    sheet,
    setSheet,
    availableSheets,
    selectedSheets,
    sheetSessions,
    sheetManifest,
    combineSheets,
    analysisScope,
    restoreState,
    eliminarDuplicados,
    setSheetStatus,
  } = useDataset()
  const [detection, setDetection] = useState<CleanResult | null>(null)
  const [rules, setRules] = useState<CleaningRules>(DEFAULT_RULES)
  const [detecting, setDetecting] = useState(false)
  const [applying, setApplying] = useState(false)
  const [cleaningProgress, setCleaningProgress] = useState<{
    current: number
    total: number
    sheet: string
  } | null>(null)
  const [applySameRules, setApplySameRules] = useState(true)
  const [downloading, setDownloading] = useState<'xlsx' | 'csv' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [persistWarning, setPersistWarning] = useState<string | null>(null)
  const [duplicateConfirmOpen, setDuplicateConfirmOpen] = useState(false)
  const [duplicateRemovalPending, setDuplicateRemovalPending] = useState(false)
  const cancelDuplicateRef = useRef<HTMLButtonElement | null>(null)
  const detectStartedFor = useRef<string | null>(null)
  const cleaningRunRef = useRef(false)
  const mappingSectionRef = useRef<HTMLDivElement | null>(null)
  const mappingNavigation = location.state as
    | { openMapping?: boolean; highlightRole?: string }
    | null
  const automaticMapping = standardization?.mapeo ?? {}
  const effectiveMapping = applyMappingOverrides(automaticMapping, mappingOverride)
  const availableColumns =
    (cleaning ?? detection)?.preview.columnas ?? standardization?.preview.columnas ?? []
  const extendedMapping = standardization?.mapeo_extendido ?? {}
  const correctedRoles = new Set(Object.keys(mappingOverride ?? {}))
  const lowConfidenceRoles = Object.entries(effectiveMapping)
    .filter(([role, column]) => {
      if (!IMPORTANT_MAPPING_ROLES.has(role)) return false
      if (correctedRoles.has(role)) return false
      const match = extendedMapping[column]
      return Boolean(
        match && match.rol_motor === role && match.confianza < MEDIUM_ROLE_CONFIDENCE,
      )
    })
    .map(([role]) => role)
  const missingAmount = Boolean(standardization && !effectiveMapping.monto)
  const highlightedRole = mappingNavigation?.highlightRole ?? (missingAmount ? 'monto' : null)
  const [mappingExpanded, setMappingExpanded] = useState(
    Boolean(mappingNavigation?.openMapping || missingAmount || lowConfidenceRoles.length),
  )
  const { plan } = usePlan()
  const basicMapping = plan === 'basico'
  const [confirmedBasicRoles, setConfirmedBasicRoles] = useState<string[]>([])
  const [basicReviewExpanded, setBasicReviewExpanded] = useState(false)

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

  const handleApplySheets = useCallback(async (
    names: string[],
    options: { retryErrors?: boolean } = {},
  ) => {
    if (!file || names.length === 0 || cleaningRunRef.current) return
    const runnable = names.filter((name) => {
      const session = sheetSessions[name]
      return Boolean(session?.standardization) &&
        !session?.cleaning &&
        (session?.status !== 'error' || options.retryErrors) &&
        session?.status !== 'limpiando'
    })
    if (runnable.length === 0) return
    const target = sheet && runnable.includes(sheet) ? sheet : runnable[0]
    // Cambiar la vista antes del resultado mantiene estandarizacion, limpieza y
    // tarjetas en la misma hoja. Antes, limpiar Mayo dejaba visible Enero.
    if (target) setSheet(target)
    cleaningRunRef.current = true
    setApplying(true)
    setError(null)
    setPersistWarning(null)
    const batchRestoreState = {
      ...restoreState,
      active_sheet: target,
      selected_sheets: [...selectedSheets],
      excluded_sheets: availableSheets.filter(
        (sheetName) => !selectedSheets.includes(sheetName),
      ),
    }
    let batchSheetErrors = { ...batchRestoreState.sheet_errors }
    try {
      for (const [index, name] of runnable.entries()) {
        const session = sheetSessions[name]
        if (!session?.standardization) continue
        setCleaningProgress({ current: index + 1, total: runnable.length, sheet: name })
        setSheetStatus(name, 'limpiando')
        // /clean solo persiste su snapshot si termina bien. Por eso el estado
        // enviado puede quitar preventivamente el error de esta hoja: si
        // falla, no se escribe y el catch lo reincorpora al mapa del lote.
        const successSheetErrors = updateBatchSheetErrors(batchSheetErrors, name, null)
        try {
          const response = await apiPost<CleanResult>(
            '/clean',
            buildDatasetForm(file, storagePath, {
              apply: 'true',
              rules: JSON.stringify(
                basicMapping || applySameRules
                  ? rules
                  : (session.cleaning?.reglas_activas ?? rules),
              ),
              // El lote conserva la decision explicita de cada hoja. Detectar
              // duplicados nunca autoriza por si solo a eliminar filas.
              eliminar_duplicados: String(session.eliminarDuplicados),
              ...(datasetId ? { dataset_id: datasetId } : {}),
              sheet: name,
              ...(session.mappingOverride
                ? { mapping: JSON.stringify(session.mappingOverride) }
                : {}),
              restore_state: JSON.stringify({
                ...batchRestoreState,
                sheet_errors: successSheetErrors,
              }),
            }),
          )
          batchSheetErrors = successSheetErrors
          setCleaning(response, { activate: name === target })
          await saveCleaningJob(datasetId, response.reglas_activas, response)
        } catch (err) {
          const message = err instanceof ApiError ? err.message : 'No se pudo limpiar esta hoja.'
          batchSheetErrors = updateBatchSheetErrors(batchSheetErrors, name, message)
          setSheetStatus(name, 'error', message)
        }
      }
    } finally {
      if (datasetId) {
        const stateForm = new FormData()
        stateForm.append('dataset_id', datasetId)
        stateForm.append('restore_state', JSON.stringify({
          ...batchRestoreState,
          sheet_errors: batchSheetErrors,
        }))
        try {
          await apiPost<Record<string, unknown>>(
            '/restore/state',
            stateForm,
            { timeoutMs: RESTORE_STATE_TIMEOUT_MS },
          )
        } catch {
          // El procesamiento ya ocurrio: un fallo al guardar la restauracion
          // no debe convertir hojas limpias en fallidas ni repetir el lote.
          setPersistWarning(
            'La limpieza termino, pero no pudimos guardar el estado final del lote. ' +
            'Si recargas ahora, puede que no aparezcan algunos errores o reintentos.',
          )
        }
      }
      cleaningRunRef.current = false
      setCleaningProgress(null)
      setApplying(false)
    }
  }, [
    applySameRules,
    availableSheets,
    basicMapping,
    datasetId,
    file,
    restoreState,
    rules,
    selectedSheets,
    setCleaning,
    setSheet,
    setSheetStatus,
    sheet,
    sheetSessions,
    storagePath,
  ])

  useEffect(() => {
    refreshUsage()
  }, [])

  useEffect(() => {
    setRules(cleaning?.reglas_activas ?? DEFAULT_RULES)
    setDirected(cleaning?.dirigida ?? null)
    setDetection(null)
    setDuplicateRemovalPending(false)
  }, [sheet, cleaning])

  useEffect(() => {
    if (!standardization) return
    if (mappingNavigation?.openMapping || missingAmount || lowConfidenceRoles.length > 0) {
      setMappingExpanded(true)
    }
    if (mappingNavigation?.openMapping) {
      requestAnimationFrame(() =>
        mappingSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }),
      )
    }
  }, [
    location.key,
    lowConfidenceRoles.join('|'),
    mappingNavigation?.openMapping,
    missingAmount,
    sheet,
    standardization,
  ])

  useEffect(() => {
    if (!duplicateConfirmOpen) return
    cancelDuplicateRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDuplicateConfirmOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [duplicateConfirmOpen])

  useEffect(() => {
    if (!file || cleaning || applying) return
    const key = [
      datasetId ?? storagePath ?? `${file.name}:${file.lastModified}:${uploadedAt?.getTime() ?? 0}`,
      sheet ?? '',
      JSON.stringify(mappingOverride ?? {}),
    ].join('|')
    if (detectStartedFor.current === key) return
    detectStartedFor.current = key
    const controller = new AbortController()
    const fields = {
      apply: 'false',
      eliminar_duplicados: 'false',
      ...(sheet ? { sheet } : {}),
      ...(mappingOverride ? { mapping: JSON.stringify(mappingOverride) } : {}),
    }
    setDetection(null)
    setDetecting(true)
    setError(null)
    apiPost<CleanResult>('/clean', buildDatasetForm(file, storagePath, fields), {
      signal: controller.signal,
    })
      .then((result) => {
        if (detectStartedFor.current === key && !controller.signal.aborted) setDetection(result)
      })
      .catch((err) => {
        if (detectStartedFor.current === key && !controller.signal.aborted) {
          setError(err instanceof ApiError ? err.message : 'No se pudo analizar el archivo.')
        }
      })
      .finally(() => {
        if (detectStartedFor.current === key && !controller.signal.aborted) setDetecting(false)
      })
    return () => {
      controller.abort()
      // Fase 12b: sin este reset, el doble montaje de StrictMode (y cualquier
      // remontaje) dejaba la clave "ya pedida" con la petición ABORTADA — la
      // página quedaba en "Analizando…" para siempre y el botón deshabilitado.
      if (detectStartedFor.current === key) detectStartedFor.current = null
    }
  }, [
    file,
    datasetId,
    storagePath,
    uploadedAt,
    cleaning,
    sheet,
    mappingOverride,
    applying,
  ])

  if (!file || !standardization) {
    // Fase 14: en modo demo se muestra un resumen READ-ONLY de la limpieza
    // ficticia (snapshot del motor real) — sin tocar el flujo interactivo.
    if (demo.active) {
      const d = demo.cleaning
      const demoProblemas: Array<{ label: string; valor: number }> = [
        { label: 'Duplicados detectados', valor: d.problemas.duplicados },
        { label: 'Valores nulos', valor: d.problemas.valores_nulos },
        { label: 'Fechas inválidas', valor: d.problemas.fechas_invalidas },
        { label: 'Textos inconsistentes', valor: d.problemas.textos_inconsistentes },
        { label: 'Tipos incorrectos', valor: d.problemas.tipos_incorrectos },
        { label: 'Montos negativos (devoluciones)', valor: d.problemas.montos_negativos ?? 0 },
      ]
      return (
        <>
          <PageHeader
            title="Limpieza de datos — demo"
            subtitle="Datos ficticios de ejemplo: así se ve el diagnóstico de limpieza de un archivo real."
          />
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-navy">{d.archivo}</h2>
                <p className="mt-0.5 text-xs text-navy/55">
                  {d.resumen.filas_antes} filas · {d.resumen.columnas_antes} columnas ·
                  calidad {d.resumen.calidad_antes}% → {d.resumen.calidad_despues}%
                </p>
              </div>
              <Badge tone="green">
                <CheckCircle2 className="h-3 w-3" /> Limpieza aplicada (demo)
              </Badge>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {demoProblemas.map(({ label, valor }) => (
                <div key={label} className="rounded-lg border border-navy/10 bg-navy/[0.02] px-3 py-2.5">
                  <p className="text-lg font-bold text-navy">{valor}</p>
                  <p className="text-xs text-navy/60">{label}</p>
                </div>
              ))}
            </div>
            <p className="mt-4 text-xs leading-relaxed text-navy/55">
              Con tus propios datos, aquí puedes revisar cada problema en detalle,
              corregir el mapeo de columnas, decidir si eliminar duplicados y
              descargar el reporte — la demo solo muestra el resultado.
            </p>
          </Card>
        </>
      )
    }
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
        >
          {/* Fase 14: conocer la plataforma sin datos propios */}
          <DemoEmptyActions />
        </EmptyState>
      </>
    )
  }

  const result = cleaning ?? detection
  const applied = cleaning !== null
  const problemCategories = result
    ? PROBLEM_LABELS.map((category) => ({
        ...category,
        value: Number(result.problemas[category.key] ?? 0),
      })).filter(({ value }) => value > 0)
    : []
  const hasProblems = problemCategories.length > 0
  const quality = result
    ? applied
      ? result.resumen.calidad_despues
      : result.resumen.calidad_antes
    : null
  const duplicateDetails = result?.duplicados_detalle
  const exactDuplicates = duplicateDetails?.exactos ?? result?.problemas.duplicados ?? 0
  const selectedDuplicates = duplicateRemovalPending
    ? exactDuplicates
    : duplicateDetails?.filas_seleccionadas_para_eliminar ?? 0
  const removedDuplicates = duplicateDetails?.filas_eliminadas ?? 0
  const granularityWarning = result?.avisos?.find((aviso) =>
    aviso.includes('variable diferenciadora'),
  )

  const semanticCandidates = (role: string) =>
    Object.entries(extendedMapping)
      .filter(
        ([, match]) =>
          match.rol_motor === role && match.confianza >= MEDIUM_ROLE_CONFIDENCE,
      )
      .map(([column]) => column)
  const assignedMappingRoles = MAPPING_ROLES.filter(({ role }) => effectiveMapping[role])
  const missingRelevantRoles = MAPPING_ROLES.filter(
    ({ role }) =>
      !effectiveMapping[role] &&
      IMPORTANT_MAPPING_ROLES.has(role) &&
      (semanticCandidates(role).length > 0 || role === highlightedRole),
  )
  const relevantMappingRoles = [...assignedMappingRoles, ...missingRelevantRoles]
  const hasMappingCorrections = correctedRoles.size > 0
  const mappingNeedsAttention = missingAmount || lowConfidenceRoles.length > 0
  const basicCriticalRoleNames = basicMappingQuestions(
    effectiveMapping,
    extendedMapping,
    confirmedBasicRoles,
  )
  const basicCriticalRoles = MAPPING_ROLES.filter(({ role }) => basicCriticalRoleNames.includes(role))
  const basicQuestion = basicCriticalRoles[0]
  const basicSelectedColumn = basicQuestion ? (effectiveMapping[basicQuestion.role] ?? '') : ''
  const basicColumnIndex = availableColumns.indexOf(basicSelectedColumn)
  const basicExamples = basicColumnIndex >= 0
    ? (standardization?.preview.despues ?? [])
        .map((row) => row[basicColumnIndex])
        .filter((value, index, values) => Boolean(value) && values.indexOf(value) === index)
        .slice(0, 5)
    : []

  const mappingFields = (): Record<string, string> => ({
    ...(mappingOverride ? { mapping: JSON.stringify(mappingOverride) } : {}),
    ...(sheet ? { sheet } : {}),
  })

  // Qué se corregirá según los toggles activos (mismo cálculo que hace la API).
  const planned = result
      ? [
        {
          label: 'Filas exactas seleccionadas para eliminar',
          value: selectedDuplicates,
        },
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
        {
          label: 'Valores atípicos señalizados (no se modifican)',
          value: rules.fuera_de_rango ? result.problemas.outliers_iqr ?? 0 : 0,
        },
      ]
    : []

  const issueMap = new Map<string, string>()
  if (result && !applied) {
    for (const issue of result.preview.issues) {
      issueMap.set(`${issue.fila}:${issue.columna}`, issue.tipo)
    }
  }

  const handleMappingChange = (role: string, column: string) => {
    if (applying || cleaningRunRef.current) return
    const nextOverride: Record<string, string> = { ...(mappingOverride ?? {}) }
    if (column) {
      // Un mismo nombre de columna no puede cumplir dos roles.
      for (const [otherRole, otherCol] of Object.entries(effectiveMapping)) {
        if (otherCol === column && otherRole !== role) nextOverride[otherRole] = ''
      }
      if (automaticMapping[role] === column) delete nextOverride[role]
      else nextOverride[role] = column
    } else {
      // Vacío explícito: el backend debe quitar el rol en vez de redetectarlo.
      nextOverride[role] = ''
    }
    const nextEffective = applyMappingOverrides(automaticMapping, nextOverride)
    const compactOverride = Object.fromEntries(
      Object.entries(nextOverride).filter(
        ([changedRole, changedColumn]) =>
          changedColumn !== automaticMapping[changedRole],
      ),
    )
    setMappingOverride(Object.keys(compactOverride).length ? compactOverride : null)
    void saveColumnMapping(datasetId, nextEffective) // best-effort (migración 0008)
  }

  const handleDownload = async (fmt: 'xlsx' | 'csv') => {
    if (!file) return
    const unfinished = selectedSheets.filter(
      (name) => !sheetSessions[name]?.cleaning || sheetSessions[name]?.status === 'error',
    )
    if (unfinished.length > 0) {
      setError(`Finaliza la limpieza de todo el alcance antes de descargar. Pendientes: ${unfinished.join(', ')}.`)
      return
    }
    setDownloading(fmt)
    setError(null)
    try {
      const stem = file.name.replace(/\.[^.]+$/, '')
      const extra: Record<string, string> = {
        rules: JSON.stringify(rules),
        eliminar_duplicados: String(eliminarDuplicados),
        fmt,
        ...mappingFields(),
      }
      if (datasetId) extra.dataset_id = datasetId
      if (directed) {
        extra.scope = JSON.stringify({
          incluir: directed.columnas_incluir,
          excluir: directed.columnas_excluir,
        })
      }
      if (sheetManifest) {
        extra.manifest = JSON.stringify(sheetManifest)
        extra.combinar_hojas = String(combineSheets)
        const serializedScope = serializedAnalysisScope(analysisScope)
        if (serializedScope) extra.analysis_scope = serializedScope
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
  const handleApply = async (removeExactDuplicates = false) => {
    setApplying(true)
    setDuplicateRemovalPending(removeExactDuplicates)
    setError(null)
    setPersistWarning(null)
    setDirected(null)
    try {
      const response = await apiPost<CleanResult>(
        '/clean',
        buildDatasetForm(file, storagePath, {
          apply: 'true',
          rules: JSON.stringify(rules),
          eliminar_duplicados: String(removeExactDuplicates),
          ...(datasetId ? { dataset_id: datasetId } : {}),
          restore_state: JSON.stringify(restoreState),
          ...mappingFields(),
        }),
      )
      await finishApply(response)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo aplicar la limpieza.')
    } finally {
      setApplying(false)
      setDuplicateRemovalPending(false)
    }
  }

  const handleConfirmedDuplicateRemoval = () => {
    setDuplicateConfirmOpen(false)
    void handleApply(true)
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
          // El texto libre nunca autoriza eliminación de filas.
          eliminar_duplicados: 'false',
          ...(datasetId ? { dataset_id: datasetId } : {}),
          restore_state: JSON.stringify(restoreState),
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
  const processedSheetCount = sheetManifest?.hojas.filter((item) => item.procesar).length ?? 0
  const unprocessedSheetCount = sheetManifest
    ? sheetManifest.hojas.length - processedSheetCount
    : 0
  const cleanedSheets = selectedSheets.filter((name) => Boolean(sheetSessions[name]?.cleaning))
  const failedSheets = selectedSheets.filter((name) => sheetSessions[name]?.status === 'error')
  const pendingSheets = selectedSheets.filter(
    (name) => !sheetSessions[name]?.cleaning && sheetSessions[name]?.status !== 'error',
  )
  const pendingPreparedSheets = pendingSheets.filter(
    (name) => Boolean(sheetSessions[name]?.standardization),
  )
  const scopeState = cleaningScopeState(selectedSheets, sheetSessions, applying)
  const cleaningComplete = scopeState === 'complete'
  const cleaningLifecycle = {
    pending: 'Pendiente',
    cleaning: 'Limpieza en curso',
    partial: 'Limpieza parcial',
    complete: 'Dataset limpio',
    complete_with_errors: 'Completa con errores',
  }[scopeState]
  const aggregateRowsAfter = selectedSheets.reduce(
    (total, name) => total + (
      sheetSessions[name]?.cleaning?.resumen.filas_despues ??
      sheetSessions[name]?.standardization?.filas ??
      0
    ),
    0,
  )

  const steps = [
    { title: 'Cargar datos', text: 'Archivo cargado', done: true, warn: false },
    {
      title: 'Revisar problemas',
      text: result ? `${problemCategories.length} categorías con observaciones` : 'Analizando…',
      done: result !== null,
      warn: result !== null && hasProblems && !applied,
    },
    { title: 'Configurar reglas', text: 'Reglas automáticas activas', done: true, warn: false },
    { title: 'Aplicar limpieza', text: cleaningLifecycle, done: cleaningComplete, warn: failedSheets.length > 0 },
    { title: 'Dataset limpio', text: cleaningComplete ? 'Listo para el análisis' : cleaningLifecycle, done: cleaningComplete, warn: failedSheets.length > 0 },
  ]

  return (
    <>
      <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <PageHeader
          className="!mb-0"
          title="Limpieza de datos ✨"
          subtitle="Revisa, ajusta y limpia tus datos para que estén listos para el análisis."
        />
        <div className="flex w-full shrink-0 flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
          {/* Fase 11 §6.2: salida explícita para estandarizar OTRO documento */}
          <Link
            to="/estandarizacion"
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-navy/20 bg-white px-4 py-2.5 text-sm font-medium text-navy transition-colors hover:bg-navy/5 sm:w-auto"
          >
            <Upload className="h-4 w-4" /> Procesar otro archivo
          </Link>
          <Link
            to="/historial"
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-navy/20 bg-white px-4 py-2.5 text-sm font-medium text-navy transition-colors hover:bg-navy/5 sm:w-auto"
          >
            <CalendarClock className="h-4 w-4" /> Historial de cargas
          </Link>
        </div>
      </div>

      {availableSheets.length > 1 && (
        <Card className="mb-4 !p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <label className="flex flex-wrap items-center gap-2 text-sm font-semibold text-navy">
              Hoja mostrada
              <select
                value={sheet ?? selectedSheets[0] ?? ''}
                onChange={(event) => setSheet(event.target.value)}
                className="max-w-full rounded-lg border border-navy/20 bg-white px-3 py-2 text-sm text-navy outline-none focus:border-teal"
              >
                {selectedSheets.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </label>
            <p className="text-xs text-navy/55">
              Las tarjetas, la vista previa y el diagnóstico son solo de esta hoja.
              El estado y los totales de todas las hojas aparecen debajo.
            </p>
          </div>
        </Card>
      )}

      {applying && cleaningProgress && (
        <div className="mb-4 flex items-center gap-3 rounded-xl border border-teal/25 bg-teal/[0.06] px-4 py-3 text-sm text-navy">
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-teal" />
          <p>
            <strong>Limpieza por lote {cleaningProgress.current} de {cleaningProgress.total}:</strong>{' '}
            {cleaningProgress.sheet}. No necesitas abrir ni limpiar las hojas una por una.
          </p>
        </div>
      )}

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
              <p className="text-xs text-navy/50">Hoja mostrada: {sheet ?? 'hoja actual'}</p>
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
              <p className="text-xs text-navy/50">Hoja mostrada: {sheet ?? 'hoja actual'}</p>
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
              <p className="mt-1 text-xs text-navy/50">Hoja mostrada: {sheet ?? 'hoja actual'}</p>
            </div>
          </div>
        </Card>
        <Card className={`!p-4 bg-gradient-to-br ${cleaningComplete ? 'from-green/[0.08]' : 'from-gold/[0.08]'} to-transparent`}>
          <div className="flex items-start gap-3">
            <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${cleaningComplete ? 'bg-green/10' : 'bg-gold/15'}`}>
              <CheckCircle2 className={`h-5 w-5 ${cleaningComplete ? 'text-green' : 'text-gold'}`} />
            </div>
            <div>
              <p className="text-xs text-navy/50">Estado</p>
              <p className="text-sm font-semibold text-navy">
                {cleaningLifecycle}
              </p>
              <p className="text-xs text-navy/50">
                {cleaningComplete
                  ? `Las ${selectedSheets.length} hojas seleccionadas están limpias.`
                  : `${cleanedSheets.length} limpias, ${pendingSheets.length} pendientes y ${failedSheets.length} con error.`}
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* Pasos de limpieza — barra horizontal compacta (Fase 8: sin columna
          lateral alargada; el ancho completo queda para los datos) */}
      {availableSheets.length > 1 && (
        <Card className="mt-6 !p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-navy">Estado de limpieza por hoja</h2>
              <p className="mt-1 text-xs text-navy/55">
                Totales de todas las hojas seleccionadas: {formatNumber(aggregateRowsAfter)} filas actuales.
              </p>
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              <Badge tone="navy">{selectedSheets.length} seleccionadas</Badge>
              <Badge tone="green">{cleanedSheets.length} limpias</Badge>
              <Badge tone="gold">{pendingSheets.length} pendientes</Badge>
              {failedSheets.length > 0 && <Badge tone="coral">{failedSheets.length} con error</Badge>}
            </div>
          </div>
          <div className="mt-3 divide-y divide-navy/10 rounded-lg border border-navy/10">
            {selectedSheets.map((name) => {
              const session = sheetSessions[name]
              const status = session?.status === 'error'
                ? 'Error'
                : session?.cleaning
                  ? 'Limpia'
                  : session?.status === 'limpiando'
                    ? 'Limpiando...'
                    : 'Pendiente'
              return (
                <div key={name} className="flex flex-wrap items-center gap-2 px-3 py-2 text-xs">
                  <button type="button" onClick={() => setSheet(name)} className="min-w-0 flex-1 truncate text-left font-semibold text-navy hover:text-teal" title={`Vista previa: ${name}`}>{name}</button>
                  {name === sheet && <span className="text-teal">Vista previa activa</span>}
                  <span className={session?.status === 'error' ? 'text-coral' : 'text-navy/55'}>{status}</span>
                </div>
              )
            })}
          </div>
          {failedSheets.length > 0 && (
            <button type="button" onClick={() => void handleApplySheets(failedSheets, { retryErrors: true })} disabled={applying} className="mt-3 inline-flex items-center gap-2 rounded-lg border border-coral/30 px-3 py-2 text-xs font-semibold text-coral disabled:opacity-50">
              {applying && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Reintentar solo las fallidas
            </button>
          )}
        </Card>
      )}

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
                    {cleaningComplete
                      ? (directed ? 'Limpieza dirigida completa ✅' : 'Todas las hojas están limpias ✅')
                      : `Hoja ${sheet ?? 'actual'} limpia; el alcance sigue en proceso`}
                  </h2>
                  <p className="mt-1 text-sm text-navy/70">
                    {cleaningComplete
                      ? 'El dataset completo ya está disponible para Resumen, Explorar y descarga. '
                      : `Estos resultados corresponden solo a ${sheet ?? 'la hoja mostrada'}. Faltan ${pendingSheets.length} hoja(s) y hay ${failedSheets.length} con error. `}
                    Calidad de esta hoja:{' '}
                    <strong>{formatNumber(result.resumen.calidad_antes)}%</strong> →{' '}
                    <strong>{formatNumber(result.resumen.calidad_despues)}%</strong>. Filas:{' '}
                    {formatNumber(result.resumen.filas_antes)} → {formatNumber(result.resumen.filas_despues)}.
                  </p>
                  {exactDuplicates > 0 && (
                    <p className="mt-2 text-sm text-navy/70">
                      Duplicados exactos: <strong>{formatNumber(exactDuplicates)} detectados</strong>
                      {' · '}
                      <strong>{formatNumber(removedDuplicates)} eliminados</strong>. Los demás se
                      conservaron.
                    </p>
                  )}
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
                      {sheetManifest
                        ? `El XLSX incluirá ${processedSheetCount} hoja(s) procesada(s) y registrará ${unprocessedSheetCount} sin procesar en Observaciones.`
                        : 'Excel con los datos intactos + hoja de Observaciones; amarillo = fecha a revisar, rojo = dato faltante.'}
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
                      disabled={downloading !== null || applying || !cleaningComplete}
                      className="inline-flex items-center gap-2 rounded-lg bg-teal px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-teal/90 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {downloading === 'xlsx' ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                      {sheetManifest ? 'Descargar libro completo' : 'Descargar base actualizada'}
                    </button>
                    <button
                      onClick={() => void handleDownload('csv')}
                      disabled={downloading !== null || applying || !cleaningComplete}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-teal/40 px-3.5 py-2.5 text-xs font-semibold text-teal transition-colors hover:bg-teal/5 disabled:cursor-not-allowed disabled:opacity-50"
                      title="Descargar datos CSV y auditoría dentro de un ZIP"
                    >
                      {downloading === 'csv' ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : null}
                      <span className="hidden">
                      {sheetManifest ? 'CSV + auditoría (hoja activa)' : 'CSV + auditoría (ZIP)'}
                      </span>
                      <span>ZIP CSV multihoja + auditoria</span>
                    </button>
                    {cleaningComplete ? (
                      <Link
                        to="/explorar"
                        className="inline-flex items-center gap-2 rounded-lg bg-navy px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-navy-deep"
                      >
                        Continuar <ArrowRight className="h-4 w-4" />
                      </Link>
                    ) : <span className="rounded-lg bg-navy/10 px-4 py-2.5 text-xs font-semibold text-navy/55">Finaliza el alcance</span>}
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
                  Vista previa: {sheet ?? standardization.carga?.hoja_usada ?? 'hoja activa'}
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
                  <div className="mt-4 rounded-lg border border-gold/40 bg-gold/10 px-4 py-3 text-sm text-navy">
                    <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
                      <p className="font-semibold">Diagnóstico por categorías</p>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {problemCategories.map(({ key, label, unit, value }) => (
                        <span key={key} className="rounded-md border border-gold/25 bg-white/70 px-2.5 py-1 text-xs text-navy/75">
                          <strong>{formatNumber(value)}</strong> {unit}: {label.toLowerCase()}
                        </span>
                      ))}
                    </div>
                    <p className="mt-2 text-xs text-navy/60">
                      Las categorías usan unidades distintas, pueden superponerse y no representan registros únicos.
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

            {result && exactDuplicates > 0 && (
              <Card className="border-coral/25 bg-gradient-to-r from-coral/[0.05] via-transparent to-transparent">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-coral/10">
                        <ShieldAlert className="h-5 w-5 text-coral" />
                      </div>
                      <div>
                        <h2 className="text-sm font-semibold text-navy">Duplicados exactos</h2>
                        <p className="text-xs text-navy/55">
                          Detectar no elimina filas. Solo se borran después de tu confirmación.
                        </p>
                      </div>
                    </div>
                    <dl className="mt-4 grid max-w-xl grid-cols-3 gap-3">
                      <div>
                        <dt className="text-[11px] text-navy/50">Detectados</dt>
                        <dd className="text-lg font-bold text-navy">{formatNumber(exactDuplicates)}</dd>
                      </div>
                      <div>
                        <dt className="text-[11px] text-navy/50">Seleccionados</dt>
                        <dd className="text-lg font-bold text-gold">{formatNumber(selectedDuplicates)}</dd>
                      </div>
                      <div>
                        <dt className="text-[11px] text-navy/50">Eliminados</dt>
                        <dd className="text-lg font-bold text-coral">{formatNumber(removedDuplicates)}</dd>
                      </div>
                    </dl>
                  </div>
                  <button
                    type="button"
                    onClick={() => setDuplicateConfirmOpen(true)}
                    disabled={applying || assistedRunning || detecting}
                    className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-coral px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-coral/90 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" />
                    Eliminar duplicados exactos ({formatNumber(exactDuplicates)})
                  </button>
                </div>
                {granularityWarning && (
                  <p className="mt-4 rounded-lg border border-gold/35 bg-gold/[0.08] px-3 py-2.5 text-xs leading-relaxed text-navy/70">
                    {granularityWarning}
                  </p>
                )}
              </Card>
            )}

            {/* Problemas / correcciones / reglas — tres columnas a lo ancho */}
            {result && (
              <div className="grid items-start gap-6 md:grid-cols-2 xl:grid-cols-3">
                <Card className="bg-gradient-to-br from-coral/[0.05] to-transparent">
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-coral/10">
                      <FileWarning className="h-4 w-4 text-coral" />
                    </div>
                    <h3 className="text-sm font-semibold text-navy">Problemas detectados</h3>
                  </div>
                  <p className="mt-1 text-[11px] text-navy/45">Hoja mostrada: {sheet ?? 'hoja actual'}</p>
                  <ul className="mt-4 space-y-2.5">
                    {PROBLEM_LABELS.map(({ key, label, unit, icon: Icon }) => (
                      <li key={key} className="flex items-center justify-between gap-2 text-sm">
                        <span className="flex items-center gap-2 text-navy/70">
                          <Icon className="h-4 w-4 text-navy/40" /> {label}
                        </span>
                        <span
                          className={`font-semibold ${
                            (result.problemas[key] ?? 0) > 0 ? 'text-coral' : 'text-navy/40'
                          }`}
                        >
                          {formatNumber(result.problemas[key] ?? 0)} {unit}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-3 text-xs leading-relaxed text-navy/45">
                    Los valores IQR son inusuales respecto de la distribución; no son necesariamente errores y no se modificarán.
                  </p>
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
                  <p className="mt-1 text-[11px] text-navy/45">Hoja mostrada: {sheet ?? 'hoja actual'}</p>
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
                    <h3 className="text-sm font-semibold text-navy">
                      Reglas automáticas (no eliminan filas)
                    </h3>
                  </div>
                  {/* Fase 12b §3: contrato honesto — la estandarización de
                      formatos ocurre SIEMPRE al cargar; estos toggles regulan
                      las correcciones ADICIONALES de la limpieza. */}
                  <p className="mt-2 text-[11px] leading-relaxed text-navy/50">
                    La estandarización de formatos (fechas, números y textos) se aplica
                    siempre al procesar el archivo. Estas reglas controlan las
                    correcciones adicionales de la limpieza.
                  </p>
                  <ul className="mt-4 space-y-3">
                    {RULE_LABELS.map(({ key, label }) => (
                      <li key={key} className="flex items-center justify-between gap-2 text-sm">
                        <span className="text-navy/70">{label}</span>
                        <Toggle
                          checked={rules[key]}
                          label={label}
                          disabled={applying}
                          onChange={(value) => {
                            if (!applying && !cleaningRunRef.current) {
                              setRules((prev) => ({ ...prev, [key]: value }))
                            }
                          }}
                        />
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>
            )}

            {/* Fase 12 B6: resumen primero; selectores solo al pedir ajuste o
                cuando falta un rol crítico / la confianza semántica es baja. */}
            <div ref={mappingSectionRef}>
              {basicMapping && (
                <Card className={mappingNeedsAttention ? 'border-gold/40' : ''}>
                  <div className="flex items-start gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-teal/10">
                      <CheckCircle2 className="h-4.5 w-4.5 text-teal" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h2 className="text-sm font-semibold text-navy">Entendimos tu archivo</h2>
                      <p className="mt-1 text-xs text-navy/55">
                        {assignedMappingRoles.length} datos identificados
                        {basicCriticalRoles.length > 0
                          ? ` · necesitamos confirmar ${basicCriticalRoles.length}`
                          : ' · no necesitas configurar nada'}
                      </p>
                    </div>
                  </div>

                  {basicQuestion && (
                    <div className="mt-4 rounded-lg border border-gold/30 bg-gold/[0.06] p-4">
                      <label className="block text-sm font-semibold text-navy" htmlFor="basic-column-question">
                        {basicQuestion.role === 'monto'
                          ? 'En que columna esta el total vendido?'
                          : 'En que columna esta la fecha de cada movimiento?'}
                      </label>
                      <select
                        id="basic-column-question"
                        value={basicSelectedColumn}
                        disabled={applying}
                        onChange={(event) => handleMappingChange(basicQuestion.role, event.target.value)}
                        className="mt-3 w-full rounded-md border border-navy/20 bg-white px-3 py-2.5 text-sm text-navy outline-none focus:border-teal disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <option value="">Seleccionar columna</option>
                        {availableColumns.map((candidate) => (
                          <option key={candidate} value={candidate}>{candidate}</option>
                        ))}
                      </select>
                      {basicExamples.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-2" aria-label="Ejemplos de la columna">
                          {basicExamples.map((example) => (
                            <span key={example} className="max-w-full truncate rounded-md bg-white px-2 py-1 text-xs text-navy/65">
                              {example}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="mt-4 flex flex-wrap gap-2">
                        <button
                          type="button"
                          disabled={!basicSelectedColumn}
                          onClick={() => setConfirmedBasicRoles((current) => [...current, basicQuestion.role])}
                          className="rounded-lg bg-teal px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
                        >
                          Confirmar y continuar
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            handleMappingChange(basicQuestion.role, '')
                            setConfirmedBasicRoles((current) => [...current, basicQuestion.role])
                          }}
                          className="rounded-lg border border-navy/15 bg-white px-4 py-2 text-xs font-semibold text-navy"
                        >
                          Mi archivo no tiene este dato
                        </button>
                      </div>
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={() => setBasicReviewExpanded((current) => !current)}
                    className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-teal"
                  >
                    {basicReviewExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    {basicReviewExpanded ? 'Ocultar interpretacion' : 'Revisar como interpretamos mi archivo'}
                  </button>
                  {basicReviewExpanded && (
                    <div className="mt-3 flex flex-wrap gap-2 border-t border-navy/10 pt-3">
                      {assignedMappingRoles.map(({ role, label }) => (
                        <span key={role} className="rounded-md bg-navy/[0.04] px-2.5 py-1 text-xs text-navy/70">
                          <strong>{label}:</strong> {effectiveMapping[role]}
                        </span>
                      ))}
                    </div>
                  )}
                </Card>
              )}
              <Card className={`${basicMapping ? 'hidden' : ''} ${mappingNeedsAttention ? 'border-gold/40' : ''}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-teal/10">
                        <Settings2 className="h-4 w-4 text-teal" />
                      </div>
                      <div>
                        <h2 className="text-sm font-semibold text-navy">Mapeo de columnas</h2>
                        <p className="mt-0.5 flex items-center gap-1 text-xs text-navy/55">
                          {mappingNeedsAttention ? (
                            <>
                              <AlertTriangle className="h-3.5 w-3.5 text-gold" />
                              Revisa los roles destacados antes de continuar.
                            </>
                          ) : (
                            <>
                              <CheckCircle2 className="h-3.5 w-3.5 text-green" />
                              {hasMappingCorrections
                                ? 'Mapeo revisado con tus correcciones.'
                                : 'Mapeo detectado automáticamente ✓'}
                            </>
                          )}
                        </p>
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {assignedMappingRoles.length > 0 ? (
                        assignedMappingRoles.map(({ role, label }) => {
                          const corrected = correctedRoles.has(role)
                          return (
                            <span
                              key={role}
                              className={`inline-flex max-w-full items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs ${
                                corrected
                                  ? 'border-gold/40 bg-gold/10 text-navy'
                                  : 'border-navy/10 bg-navy/[0.04] text-navy/75'
                              }`}
                              title={corrected ? 'Corregido por ti' : 'Detectado automáticamente'}
                            >
                              <strong>{label}</strong>
                              <span aria-hidden="true">→</span>
                              <span className="max-w-52 truncate">{effectiveMapping[role]}</span>
                              {corrected && <span className="font-semibold text-gold">corregido por ti</span>}
                            </span>
                          )
                        })
                      ) : (
                        <span className="text-xs text-navy/50">No hay roles asignados todavía.</span>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setMappingExpanded((current) => !current)}
                    aria-expanded={mappingExpanded}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-teal/40 px-3 py-2 text-xs font-semibold text-teal transition-colors hover:bg-teal/5"
                  >
                    {mappingExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    {mappingExpanded ? 'Ocultar ajustes' : 'Ajustar'}
                  </button>
                </div>

                {mappingExpanded && (
                  <div className="mt-5 border-t border-navy/10 pt-1">
                    <div className="grid gap-x-6 md:grid-cols-2">
                      {relevantMappingRoles.map(({ role, label, description }) => {
                        const column = effectiveMapping[role] ?? ''
                        const match = column ? extendedMapping[column] : undefined
                        const corrected = correctedRoles.has(role)
                        const lowConfidence =
                          !corrected &&
                          Boolean(match && match.confianza < MEDIUM_ROLE_CONFIDENCE)
                        const highlighted = role === highlightedRole || lowConfidence
                        const candidates = new Set(semanticCandidates(role))
                        return (
                          <label
                            key={role}
                            className={`grid gap-2 border-b border-navy/10 py-4 ${
                              highlighted ? 'bg-gold/[0.07] px-3' : ''
                            }`}
                          >
                            <span>
                              <span className="flex flex-wrap items-center gap-2 text-sm font-semibold text-navy">
                                {label}
                                {corrected && (
                                  <span className="rounded-md bg-gold/15 px-2 py-0.5 text-[11px] text-navy">
                                    Corregido por ti
                                  </span>
                                )}
                                {lowConfidence && (
                                  <span className="rounded-md bg-coral/10 px-2 py-0.5 text-[11px] text-coral">
                                    Confianza baja
                                  </span>
                                )}
                              </span>
                              <span className="mt-0.5 block text-xs text-navy/55">{description}</span>
                            </span>
                            <select
                              value={column}
                              disabled={applying}
                              onChange={(event) => handleMappingChange(role, event.target.value)}
                              className="w-full rounded-md border border-navy/20 bg-white px-3 py-2 text-sm text-navy outline-none focus:border-teal disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              <option value="">Sin asignar</option>
                              {availableColumns.map((candidate) => (
                                <option key={candidate} value={candidate}>
                                  {candidate}{candidates.has(candidate) ? ' · sugerida por el motor' : ''}
                                </option>
                              ))}
                            </select>
                            <span className="text-[11px] text-navy/45">
                              {corrected
                                ? 'Asignación manual guardada para este dataset.'
                                : match
                                  ? `Confianza del rol ${Math.round(match.confianza * 100)}% · método ${match.metodo}.`
                                  : column
                                    ? 'El detector legacy asignó este rol sin una confianza semántica comparable.'
                                    : 'Elige una columna solo si conoces su significado en tu negocio.'}
                            </span>
                          </label>
                        )
                      })}
                    </div>
                    <p className="mt-3 text-xs text-navy/55">
                      Al cambiar una asignación, la limpieza y los indicadores se recalculan
                      con el nuevo mapeo.
                    </p>
                  </div>
                )}
              </Card>
            </div>
          </>
        )}

        {/* Barra de acción: botón "Limpiar datos" (todos los planes) */}
        {!cleaningComplete && (
          <Card className="!p-4 bg-gradient-to-r from-teal/[0.04] to-transparent">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-navy">Todo listo para limpiar</p>
                <p className="mt-1 text-xs text-navy/55">
                  {selectedSheets.length > 1
                    ? `Al continuar, limpiaremos una por una las ${pendingPreparedSheets.length} hojas pendientes de las ${selectedSheets.length} seleccionadas.`
                    : 'Aplicaremos las reglas elegidas a esta hoja. Nada se modifica hasta que pulses el botón.'}
                </p>
              </div>
              {selectedSheets.length > 1 && (
                <div className="flex flex-wrap items-center justify-end gap-2">
                  {!basicMapping && (
                    <label className="mr-auto flex items-center gap-2 text-xs text-navy/65">
                      <input
                        type="checkbox"
                        checked={applySameRules}
                        onChange={(event) => setApplySameRules(event.target.checked)}
                        className="h-4 w-4 accent-teal"
                      />
                      Aplicar las mismas reglas a todas
                    </label>
                  )}
                  <button
                    type="button"
                    onClick={() => void handleApplySheets(pendingPreparedSheets)}
                    disabled={applying || detecting || !result || pendingPreparedSheets.length === 0}
                    className="inline-flex items-center gap-2 rounded-lg bg-teal px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
                  >
                    {applying && <Loader2 className="h-4 w-4 animate-spin" />}
                    {applying ? 'Limpiando datos...' : 'Limpiar datos'}
                  </button>
                </div>
              )}
              <button
                onClick={() => void handleApply()}
                disabled={applying || assistedRunning || detecting || !result}
                className={`${selectedSheets.length > 1 ? 'hidden' : 'inline-flex'} items-center gap-2 rounded-lg bg-teal px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-teal/90 disabled:cursor-not-allowed disabled:bg-teal/50`}
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
              <em>"limpia Fecha y Ventas, no toques Cliente"</em>) y la
              plataforma dirige la limpieza con tus instrucciones.
            </p>
            <p className="mt-1 text-xs text-navy/50">
              Las instrucciones pueden detectar duplicados, pero nunca autorizan eliminarlos.
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

      {duplicateConfirmOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-navy-deep/55 p-4"
          onMouseDown={() => setDuplicateConfirmOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="duplicate-confirm-title"
            className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-coral/10">
                <ShieldAlert className="h-5 w-5 text-coral" />
              </div>
              <div>
                <h2 id="duplicate-confirm-title" className="text-base font-semibold text-navy">
                  ¿Eliminar {formatNumber(exactDuplicates)} duplicados exactos?
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-navy/70">
                  Se eliminarán solo las repeticiones que ya eran idénticas en el archivo
                  original. Las coincidencias creadas por normalización se conservarán.
                </p>
              </div>
            </div>
            <p className="mt-4 rounded-lg border border-gold/40 bg-gold/[0.09] px-3 py-3 text-xs leading-relaxed text-navy/75">
              {granularityWarning ??
                'Dos filas idénticas pueden ser registros legítimos si el archivo omitió una variable diferenciadora. Verifica el origen antes de continuar.'}
            </p>
            <p className="mt-3 text-xs font-medium text-coral">
              Esta acción modifica la base procesada y no se puede deshacer dentro de esta sesión.
            </p>
            <div className="mt-5 flex justify-end gap-2.5">
              <button
                ref={cancelDuplicateRef}
                type="button"
                onClick={() => setDuplicateConfirmOpen(false)}
                className="rounded-lg border border-navy/20 bg-white px-4 py-2 text-sm font-semibold text-navy transition-colors hover:bg-navy/5"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleConfirmedDuplicateRemoval}
                className="inline-flex items-center gap-2 rounded-lg bg-coral px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-coral/90"
              >
                <Trash2 className="h-4 w-4" />
                Eliminar duplicados exactos
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
