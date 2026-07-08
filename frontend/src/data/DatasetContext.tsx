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
import type { CleanResult, MetricsResult, StandardizeResult } from '../lib/types'

/** Rango de fechas activo del topbar; null = todo el periodo. */
export interface Period {
  from: string | null // YYYY-MM-DD
  to: string | null
  label: string
}

export const ALL_PERIOD: Period = { from: null, to: null, label: 'Todo el periodo' }

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
  setUploaded: (file: File, datasetId: string | null, storagePath: string | null) => void
  setStandardization: (result: StandardizeResult) => void
  setCleaning: (result: CleanResult) => void
  setMetrics: (result: MetricsResult) => void
  setPeriod: (period: Period) => void
  setMonthsAvailable: (months: string[]) => void
  setMappingOverride: (mapping: Record<string, string> | null) => void
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
  const [mappingOverride, setMappingOverride] = useState<Record<string, string> | null>(null)

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
      setMappingOverride(null)
    },
    [],
  )

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
    setMappingOverride(null)
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
      setUploaded,
      setStandardization: setStandardizationState,
      setCleaning: setCleaningState,
      setMetrics: setMetricsState,
      setPeriod,
      setMonthsAvailable,
      setMappingOverride,
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
      setUploaded,
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
