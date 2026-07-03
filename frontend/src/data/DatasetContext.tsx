import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { CleanResult, StandardizeResult } from '../lib/types'

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
  uploadedAt: Date | null
  period: Period
  monthsAvailable: string[]
  setUploaded: (file: File, datasetId: string | null, storagePath: string | null) => void
  setStandardization: (result: StandardizeResult) => void
  setCleaning: (result: CleanResult) => void
  setPeriod: (period: Period) => void
  setMonthsAvailable: (months: string[]) => void
  reset: () => void
}

const DatasetContext = createContext<DatasetState | undefined>(undefined)

export function DatasetProvider({ children }: { children: ReactNode }) {
  const [file, setFile] = useState<File | null>(null)
  const [datasetId, setDatasetId] = useState<string | null>(null)
  const [storagePath, setStoragePath] = useState<string | null>(null)
  const [standardization, setStandardizationState] = useState<StandardizeResult | null>(null)
  const [cleaning, setCleaningState] = useState<CleanResult | null>(null)
  const [uploadedAt, setUploadedAt] = useState<Date | null>(null)
  const [period, setPeriod] = useState<Period>(ALL_PERIOD)
  const [monthsAvailable, setMonthsAvailable] = useState<string[]>([])

  const setUploaded = useCallback(
    (newFile: File, newDatasetId: string | null, newStoragePath: string | null) => {
      setFile(newFile)
      setDatasetId(newDatasetId)
      setStoragePath(newStoragePath)
      setStandardizationState(null)
      setCleaningState(null)
      setUploadedAt(new Date())
      setPeriod(ALL_PERIOD)
      setMonthsAvailable([])
    },
    [],
  )

  const reset = useCallback(() => {
    setFile(null)
    setDatasetId(null)
    setStoragePath(null)
    setStandardizationState(null)
    setCleaningState(null)
    setUploadedAt(null)
    setPeriod(ALL_PERIOD)
    setMonthsAvailable([])
  }, [])

  const value = useMemo(
    () => ({
      file,
      datasetId,
      storagePath,
      standardization,
      cleaning,
      uploadedAt,
      period,
      monthsAvailable,
      setUploaded,
      setStandardization: setStandardizationState,
      setCleaning: setCleaningState,
      setPeriod,
      setMonthsAvailable,
      reset,
    }),
    [
      file,
      datasetId,
      storagePath,
      standardization,
      cleaning,
      uploadedAt,
      period,
      monthsAvailable,
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
