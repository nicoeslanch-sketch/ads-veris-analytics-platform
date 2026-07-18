import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useAuth } from '../auth/AuthContext'
import type {
  AnalysisScope,
  CleanResult,
  MetricsResult,
  SheetManifest,
  SheetProcessingStatus,
  StandardizeResult,
} from '../lib/types'

/** Rango de fechas activo del topbar; null = todo el periodo. */
export interface Period {
  from: string | null // YYYY-MM-DD
  to: string | null
  label: string
}

export const ALL_PERIOD: Period = { from: null, to: null, label: 'Todo el periodo' }

export interface SheetSession {
  standardization: StandardizeResult | null
  cleaning: CleanResult | null
  mappingOverride: Record<string, string> | null
  eliminarDuplicados: boolean
  status: SheetProcessingStatus
  error: string | null
}

export interface DatasetRestoreState {
  active_sheet: string | null
  available_sheets: string[]
  excluded_sheets: string[]
  selected_sheets: string[]
  sheet_errors: Record<string, string>
  analysis_scope: AnalysisScope | null
  combine_sheets: boolean
  selection_mode: 'all' | 'custom'
}

export interface RestoreDatasetOptions {
  activeSheet: string | null
  availableSheets: string[]
  combineSheets: boolean
  sheetSessions: Record<string, SheetSession>
  selectedSheets?: string[]
  sheetErrors?: Record<string, string>
  analysisScope?: AnalysisScope | null
  selectionMode?: 'all' | 'custom'
}

/** Construye el periodo de un mes "YYYY-MM" (primer al último día). */
export function monthPeriod(isoMonth: string): Period {
  const [year, month] = isoMonth.split('-').map(Number)
  const lastDay = new Date(year, month, 0).getDate()
  const name = new Date(year, month - 1, 1).toLocaleDateString('es-CL', {
    month: 'short',
    year: 'numeric',
  })
  return {
    from: `${isoMonth}-01`,
    to: `${isoMonth}-${String(lastDay).padStart(2, '0')}`,
    label: `01 ${name.replace(' de ', ' ')} - ${lastDay} ${name.replace(' de ', ' ')}`,
  }
}

/** Construye el periodo que cubre TODO el dataset: desde el primer día del
 * primer mes con datos hasta el último día del último mes (Bug #2: antes el
 * default caía en un solo mes y dejaba fuera datos reales del archivo). */
export function fullRangePeriod(months: string[]): Period {
  if (months.length === 0) return ALL_PERIOD
  const first = months[0]
  const last = months[months.length - 1]
  const [lastYear, lastMonth] = last.split('-').map(Number)
  const lastDay = new Date(lastYear, lastMonth, 0).getDate()
  const nameOf = (isoMonth: string) => {
    const [y, m] = isoMonth.split('-').map(Number)
    return new Date(y, m - 1, 1)
      .toLocaleDateString('es-CL', { month: 'short', year: 'numeric' })
      .replace(' de ', ' ')
  }
  return {
    from: `${first}-01`,
    to: `${last}-${String(lastDay).padStart(2, '0')}`,
    label: `01 ${nameOf(first)} - ${lastDay} ${nameOf(last)}`,
  }
}

/**
 * Estado del dataset de la sesión, compartido entre Estandarización, Limpieza
 * y el resto de módulos. El archivo vive en memoria (los endpoints son
 * stateless); la persistencia en Supabase es best-effort (lib/datasets.ts).
 */
interface DatasetState {
  file: File | null
  datasetId: string | null
  storagePath: string | null
  standardization: StandardizeResult | null
  cleaning: CleanResult | null
  metrics: MetricsResult | null
  uploadedAt: Date | null
  period: Period
  monthsAvailable: string[]
  /** Roles de negocio corregidos por el usuario en Limpieza (Fase 7 §5.10);
   * null = usar el mapeo automático. Lo respetan /clean, /metrics y descargas. */
  mappingOverride: Record<string, string> | null
  /** Decisión explícita de la sesión; nunca se infiere desde rules. */
  eliminarDuplicados: boolean
  /** Hoja de Excel elegida por el usuario (Fase 10 §8.3); null = automática.
   * Cambiarla invalida limpieza y métricas (los datos son otros). */
  sheet: string | null
  availableSheets: string[]
  sheetSessions: Record<string, SheetSession>
  selectedSheets: string[]
  sheetErrors: Record<string, string>
  analysisScope: AnalysisScope | null
  sheetManifest: SheetManifest | null
  combineSheets: boolean
  selectionMode: 'all' | 'custom'
  restoreState: DatasetRestoreState
  /** true mientras DatasetBootstrap restaura el último trabajo al iniciar
   * sesión/recargar — otros componentes (sidebar, selector de periodo,
   * cupos) lo usan para mostrar un estado de carga en vez de un valor por
   * defecto que luego cambia (Bug: "Sin fuentes conectadas" parpadeaba
   * antes de que apareciera el archivo real). */
  restoring: boolean
  setRestoring: (value: boolean) => void
  setSheet: (sheet: string | null) => void
  setUploaded: (file: File, datasetId: string | null, storagePath: string | null) => void
  restoreDataset: (
    file: File,
    datasetId: string,
    storagePath: string,
    standardization: StandardizeResult,
    cleaning: CleanResult | null,
    metrics: MetricsResult | null,
    mappingOverride: Record<string, string> | null,
    eliminarDuplicados: boolean,
    options?: RestoreDatasetOptions,
  ) => void
  setStandardization: (result: StandardizeResult, options?: { activate?: boolean }) => void
  setCleaning: (result: CleanResult, options?: { activate?: boolean }) => void
  setMetrics: (result: MetricsResult) => void
  setPeriod: (period: Period) => void
  setMonthsAvailable: (months: string[]) => void
  setMappingOverride: (mapping: Record<string, string> | null) => void
  setEliminarDuplicados: (value: boolean) => void
  setCombineSheets: (value: boolean) => void
  setSelectionMode: (value: 'all' | 'custom') => void
  setSelectedSheets: (sheets: string[]) => void
  setAnalysisScope: (scope: AnalysisScope) => void
  setSheetStatus: (
    sheet: string,
    status: SheetProcessingStatus,
    error?: string | null,
  ) => void
  reset: () => void
}

const DatasetContext = createContext<DatasetState | undefined>(undefined)

export function DatasetProvider({ children }: { children: ReactNode }) {
  const [file, setFile] = useState<File | null>(null)
  const [datasetId, setDatasetId] = useState<string | null>(null)
  const [storagePath, setStoragePath] = useState<string | null>(null)
  const [standardization, setStandardizationState] = useState<StandardizeResult | null>(null)
  const [cleaning, setCleaningState] = useState<CleanResult | null>(null)
  const [metrics, setMetricsState] = useState<MetricsResult | null>(null)
  const [uploadedAt, setUploadedAt] = useState<Date | null>(null)
  const [period, setPeriod] = useState<Period>(ALL_PERIOD)
  const [monthsAvailable, setMonthsAvailable] = useState<string[]>([])
  const [mappingOverride, setMappingOverrideState] = useState<Record<string, string> | null>(null)
  const [sheet, setSheetState] = useState<string | null>(null)
  const [eliminarDuplicados, setEliminarDuplicados] = useState(false)
  const [availableSheets, setAvailableSheets] = useState<string[]>([])
  const [sheetSessions, setSheetSessions] = useState<Record<string, SheetSession>>({})
  const [selectedSheets, setSelectedSheetsState] = useState<string[]>([])
  const [sheetErrors, setSheetErrors] = useState<Record<string, string>>({})
  const [analysisScope, setAnalysisScopeState] = useState<AnalysisScope | null>(null)
  const [combineSheets, setCombineSheets] = useState(false)
  const [selectionMode, setSelectionMode] = useState<'all' | 'custom'>('all')
  const [restoring, setRestoring] = useState(false)

  // Cada hoja mantiene su propia configuración. Al activarla se restaura solo
  // su estado; métricas y periodo siempre se recalculan para evitar mezclas.
  const setSheet = useCallback((newSheet: string | null) => {
    const session = newSheet ? sheetSessions[newSheet] : undefined
    setSheetState(newSheet)
    setStandardizationState(session?.standardization ?? null)
    setCleaningState(session?.cleaning ?? null)
    setMetricsState(null)
    setMonthsAvailable([])
    setPeriod(ALL_PERIOD)
    setMappingOverrideState(session?.mappingOverride ?? null)
    setEliminarDuplicados(session?.eliminarDuplicados ?? false)
  }, [sheetSessions])

  const setStandardization = useCallback((
    result: StandardizeResult,
    options: { activate?: boolean } = {},
  ) => {
    const activeSheet = result.carga?.hoja_usada ?? null
    const sheets = result.carga?.hojas_disponibles ?? []
    const activate = options.activate !== false
    if (activate) setStandardizationState(result)
    if (sheets.length) setAvailableSheets(sheets)
    if (!activeSheet) return
    if (activate) setSheetState(activeSheet)
    setSheetSessions((previous) => ({
      ...previous,
      [activeSheet]: {
        standardization: result,
        cleaning: previous[activeSheet]?.cleaning ?? null,
        mappingOverride: previous[activeSheet]?.mappingOverride ?? null,
        eliminarDuplicados: previous[activeSheet]?.eliminarDuplicados ?? false,
        status: 'estandarizada',
        error: null,
      },
    }))
    setSheetErrors((previous) => {
      const next = { ...previous }
      delete next[activeSheet]
      return next
    })
    const recommended = (result.carga?.clasificacion_hojas ?? [])
      .filter((profile) => profile.recomendacion === 'procesar')
      .map((profile) => profile.nombre)
      .filter((name) => sheets.includes(name))
    setSelectedSheetsState((previous) => (
      previous.length
        ? previous
        : (recommended.length ? recommended : (sheets.length ? sheets : [activeSheet]))
    ))
    setAnalysisScopeState((previous) => previous ?? {
      mode: 'single',
      sheets: [activeSheet],
      active_sheet: activeSheet,
    })
  }, [])

  const setCleaning = useCallback((
    result: CleanResult,
    options: { activate?: boolean } = {},
  ) => {
    const activeSheet = result.carga?.hoja_usada ?? sheet
    const removeDuplicates = Boolean(result.opciones_aplicacion?.eliminar_duplicados)
    const activate = options.activate !== false
    if (activate) {
      setCleaningState(result)
      setMetricsState(null)
      setMonthsAvailable([])
      setPeriod(ALL_PERIOD)
      setEliminarDuplicados(removeDuplicates)
    }
    if (activeSheet) {
      setSheetSessions((previous) => ({
        ...previous,
        [activeSheet]: {
          standardization: previous[activeSheet]?.standardization ?? standardization,
          cleaning: result,
          mappingOverride: previous[activeSheet]?.mappingOverride ?? mappingOverride,
          eliminarDuplicados: removeDuplicates,
          status: 'limpia',
          error: null,
        },
      }))
    }
  }, [mappingOverride, sheet, standardization])

  const setMappingOverride = useCallback((mapping: Record<string, string> | null) => {
    setMappingOverrideState(mapping)
    setCleaningState(null)
    setMetricsState(null)
    setMonthsAvailable([])
    setPeriod(ALL_PERIOD)
    if (sheet) {
      setSheetSessions((previous) => ({
        ...previous,
        [sheet]: {
          standardization: previous[sheet]?.standardization ?? standardization,
          cleaning: null,
          mappingOverride: mapping,
          eliminarDuplicados: previous[sheet]?.eliminarDuplicados ?? eliminarDuplicados,
          status: previous[sheet]?.status ?? 'estandarizada',
          error: previous[sheet]?.error ?? null,
        },
      }))
    }
  }, [eliminarDuplicados, sheet, standardization])

  const updateEliminarDuplicados = useCallback((value: boolean) => {
    setEliminarDuplicados(value)
    if (sheet) {
      setSheetSessions((previous) => ({
        ...previous,
        [sheet]: {
          standardization: previous[sheet]?.standardization ?? standardization,
          cleaning: previous[sheet]?.cleaning ?? cleaning,
          mappingOverride: previous[sheet]?.mappingOverride ?? mappingOverride,
          eliminarDuplicados: value,
          status: previous[sheet]?.status ?? 'estandarizada',
          error: previous[sheet]?.error ?? null,
        },
      }))
    }
  }, [cleaning, mappingOverride, sheet, standardization])

  const setUploaded = useCallback(
    (newFile: File, newDatasetId: string | null, newStoragePath: string | null) => {
      setFile(newFile)
      setDatasetId(newDatasetId)
      setStoragePath(newStoragePath)
      setStandardizationState(null)
      setCleaningState(null)
      setMetricsState(null)
      setUploadedAt(new Date())
      setPeriod(ALL_PERIOD)
      setMonthsAvailable([])
      setMappingOverrideState(null)
      setSheetState(null)
      setEliminarDuplicados(false)
      setAvailableSheets([])
      setSheetSessions({})
      setSelectedSheetsState([])
      setSheetErrors({})
      setAnalysisScopeState(null)
      setCombineSheets(false)
      setSelectionMode('all')
    },
    [],
  )

  /** Rehydrate the complete pipeline in one render. */
  const restoreDataset = useCallback((
    restoredFile: File,
    restoredDatasetId: string,
    restoredStoragePath: string,
    restoredStandardization: StandardizeResult,
    restoredCleaning: CleanResult | null,
    restoredMetrics: MetricsResult | null,
    restoredMapping: Record<string, string> | null,
    restoredEliminarDuplicados: boolean,
    options?: RestoreDatasetOptions,
  ) => {
    const inferredActiveSheet =
      restoredCleaning?.carga?.hoja_usada ??
      restoredStandardization.carga?.hoja_usada ??
      null
    const sheets = restoredStandardization.carga?.hojas_disponibles ?? []
    const restoredSession: SheetSession = {
      standardization: restoredStandardization,
      cleaning: restoredCleaning,
      mappingOverride: restoredMapping,
      eliminarDuplicados: restoredEliminarDuplicados,
      status: restoredCleaning ? 'limpia' : 'estandarizada',
      error: null,
    }
    const activeSheet = options?.activeSheet ?? inferredActiveSheet
    const sessions = { ...(options?.sheetSessions ?? {}) }
    if (activeSheet && !sessions[activeSheet]) sessions[activeSheet] = restoredSession
    const activeSession = activeSheet ? sessions[activeSheet] : undefined

    setFile(restoredFile)
    setDatasetId(restoredDatasetId)
    setStoragePath(restoredStoragePath)
    setStandardizationState(activeSession?.standardization ?? restoredStandardization)
    setCleaningState(activeSession?.cleaning ?? restoredCleaning)
    setMetricsState(restoredMetrics)
    setUploadedAt(new Date())
    setPeriod(ALL_PERIOD)
    setMonthsAvailable(restoredMetrics?.periodo.meses_disponibles ?? [])
    setMappingOverrideState(activeSession?.mappingOverride ?? restoredMapping)
    setSheetState(activeSheet)
    setEliminarDuplicados(activeSession?.eliminarDuplicados ?? restoredEliminarDuplicados)
    setAvailableSheets(options?.availableSheets ?? sheets)
    setSheetSessions(sessions)
    setSelectedSheetsState(options?.selectedSheets ?? (options?.availableSheets ?? sheets))
    setSheetErrors(options?.sheetErrors ?? {})
    setAnalysisScopeState(options?.analysisScope ?? (
      activeSheet ? { mode: 'single', sheets: [activeSheet], active_sheet: activeSheet } : null
    ))
    setCombineSheets(Boolean(options?.combineSheets))
    setSelectionMode(options?.selectionMode ?? 'all')
  }, [])

  const reset = useCallback(() => {
    setFile(null)
    setDatasetId(null)
    setStoragePath(null)
    setStandardizationState(null)
    setCleaningState(null)
    setMetricsState(null)
    setUploadedAt(null)
    setPeriod(ALL_PERIOD)
    setMonthsAvailable([])
    setMappingOverrideState(null)
    setSheetState(null)
    setEliminarDuplicados(false)
    setAvailableSheets([])
    setSheetSessions({})
    setSelectedSheetsState([])
    setSheetErrors({})
    setAnalysisScopeState(null)
    setCombineSheets(false)
    setSelectionMode('all')
  }, [])

  // Al cerrar sesión o cambiar de usuario en el mismo navegador, el dataset
  // de la sesión anterior no debe seguir vivo (archivos, métricas ni panel IA).
  const { user } = useAuth()
  const userId = user?.id ?? null
  const lastUserId = useRef<string | null | undefined>(undefined)
  useEffect(() => {
    if (lastUserId.current !== undefined && lastUserId.current !== userId) {
      reset()
    }
    lastUserId.current = userId
  }, [userId, reset])

  const setSelectedSheets = useCallback((names: string[]) => {
    const unique = names.filter(
      (name, index) => availableSheets.includes(name) && names.indexOf(name) === index,
    )
    setSelectedSheetsState(unique)
    setSheetSessions((previous) => {
      const next = { ...previous }
      for (const name of availableSheets) {
        const current = next[name]
        if (current) {
          next[name] = {
            ...current,
            status: unique.includes(name)
              ? (current.status === 'no_seleccionada' ? 'pendiente' : current.status)
              : 'no_seleccionada',
          }
        }
      }
      return next
    })
    setAnalysisScopeState((current) => {
      if (current && current.sheets.every((name) => unique.includes(name))) return current
      const active = unique[0]
      return active ? { mode: 'single', sheets: [active], active_sheet: active } : null
    })
  }, [availableSheets])

  const setSheetStatus = useCallback((
    name: string,
    status: SheetProcessingStatus,
    error: string | null = null,
  ) => {
    setSheetSessions((previous) => ({
      ...previous,
      [name]: {
        standardization: previous[name]?.standardization ?? null,
        cleaning: previous[name]?.cleaning ?? null,
        mappingOverride: previous[name]?.mappingOverride ?? null,
        eliminarDuplicados: previous[name]?.eliminarDuplicados ?? false,
        status,
        error,
      },
    }))
    setSheetErrors((previous) => {
      const next = { ...previous }
      if (error) next[name] = error
      else delete next[name]
      return next
    })
  }, [])

  const setAnalysisScope = useCallback((scope: AnalysisScope) => {
    setAnalysisScopeState(scope)
    setMetricsState(null)
    setMonthsAvailable([])
    setPeriod(ALL_PERIOD)
  }, [])

  const sheetManifest = useMemo<SheetManifest | null>(() => {
    if (availableSheets.length <= 1) return null
    return {
      hojas: availableSheets.map((name) => {
        const session = sheetSessions[name]
        const directed = session?.cleaning?.dirigida
        return {
          nombre: name,
          procesar: selectedSheets.includes(name) && Boolean(session?.standardization),
          rules: session?.cleaning?.reglas_activas ?? {},
          mapping: session?.mappingOverride ?? {},
          scope: directed
            ? { incluir: directed.columnas_incluir, excluir: directed.columnas_excluir }
            : {},
          eliminar_duplicados: session?.eliminarDuplicados ?? false,
          status: session?.status ?? (selectedSheets.includes(name) ? 'pendiente' : 'no_seleccionada'),
          error: session?.error ?? sheetErrors[name] ?? '',
          revision: session?.cleaning?.revision ?? session?.standardization?.revision ?? 0,
        }
      }),
    }
  }, [availableSheets, selectedSheets, sheetErrors, sheetSessions])

  const restoreState = useMemo<DatasetRestoreState>(() => ({
    active_sheet: sheet,
    available_sheets: availableSheets,
    excluded_sheets: availableSheets.filter(
      (name) => !selectedSheets.includes(name),
    ),
    selected_sheets: selectedSheets,
    sheet_errors: sheetErrors,
    analysis_scope: analysisScope,
    combine_sheets: combineSheets,
    selection_mode: selectionMode,
  }), [analysisScope, availableSheets, combineSheets, selectedSheets, selectionMode, sheet, sheetErrors])

  const value = useMemo(
    () => ({
      file,
      datasetId,
      storagePath,
      standardization,
      cleaning,
      metrics,
      uploadedAt,
      period,
      monthsAvailable,
      mappingOverride,
      eliminarDuplicados,
      sheet,
      availableSheets,
      sheetSessions,
      selectedSheets,
      sheetErrors,
      analysisScope,
      sheetManifest,
      combineSheets,
      selectionMode,
      restoreState,
      restoring,
      setRestoring,
      setSheet,
      setUploaded,
      restoreDataset,
      setStandardization,
      setCleaning,
      setMetrics: setMetricsState,
      setPeriod,
      setMonthsAvailable,
      setMappingOverride,
      setEliminarDuplicados: updateEliminarDuplicados,
      setCombineSheets,
      setSelectionMode,
      setSelectedSheets,
      setAnalysisScope,
      setSheetStatus,
      reset,
    }),
    [
      file,
      datasetId,
      storagePath,
      standardization,
      cleaning,
      metrics,
      uploadedAt,
      period,
      monthsAvailable,
      mappingOverride,
      eliminarDuplicados,
      sheet,
      availableSheets,
      sheetSessions,
      selectedSheets,
      sheetErrors,
      analysisScope,
      sheetManifest,
      combineSheets,
      selectionMode,
      restoreState,
      restoring,
      setSheet,
      setUploaded,
      restoreDataset,
      setStandardization,
      setMappingOverride,
      setCleaning,
      updateEliminarDuplicados,
      setSelectedSheets,
      setAnalysisScope,
      setSheetStatus,
      reset,
    ],
  )

  return <DatasetContext.Provider value={value}>{children}</DatasetContext.Provider>
}

export function useDataset(): DatasetState {
  const ctx = useContext(DatasetContext)
  if (!ctx) throw new Error('useDataset debe usarse dentro de <DatasetProvider>')
  return ctx
}
