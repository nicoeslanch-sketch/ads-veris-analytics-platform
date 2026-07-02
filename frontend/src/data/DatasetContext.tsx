import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { CleanResult, StandardizeResult } from '../lib/types'

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
  setUploaded: (file: File, datasetId: string | null, storagePath: string | null) => void
  setStandardization: (result: StandardizeResult) => void
  setCleaning: (result: CleanResult) => void
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

  const setUploaded = useCallback(
    (newFile: File, newDatasetId: string | null, newStoragePath: string | null) => {
      setFile(newFile)
      setDatasetId(newDatasetId)
      setStoragePath(newStoragePath)
      setStandardizationState(null)
      setCleaningState(null)
      setUploadedAt(new Date())
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
  }, [])

  const value = useMemo(
    () => ({
      file,
      datasetId,
      storagePath,
      standardization,
      cleaning,
      uploadedAt,
      setUploaded,
      setStandardization: setStandardizationState,
      setCleaning: setCleaningState,
      reset,
    }),
    [file, datasetId, storagePath, standardization, cleaning, uploadedAt, setUploaded, reset],
  )

  return <DatasetContext.Provider value={value}>{children}</DatasetContext.Provider>
}

export function useDataset(): DatasetState {
  const ctx = useContext(DatasetContext)
  if (!ctx) throw new Error('useDataset debe usarse dentro de <DatasetProvider>')
  return ctx
}
