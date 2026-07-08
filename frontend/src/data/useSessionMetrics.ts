/** Métricas del dataset de la sesión para páginas que las consumen completas
 * (Alertas, Reportes). Reusa las del contexto si existen; si no, las calcula
 * una vez (todo el periodo) y las comparte de vuelta al contexto. */

import { useEffect, useRef, useState } from 'react'
import { ApiError, apiPost, buildDatasetForm } from '../lib/api'
import type { MetricsResult } from '../lib/types'
import { useDataset } from './DatasetContext'

export function useSessionMetrics(): {
  ready: boolean
  metrics: MetricsResult | null
  loading: boolean
  error: string | null
} {
  const { file, cleaning, datasetId, storagePath, uploadedAt, metrics, setMetrics, mappingOverride } =
    useDataset()
  const ready = Boolean(file && cleaning)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fetchedFor = useRef<string | null>(null)

  useEffect(() => {
    if (!file || !cleaning || metrics) return
    const key = datasetId ?? storagePath ?? String(uploadedAt?.getTime() ?? 0)
    if (fetchedFor.current === key) return
    fetchedFor.current = key
    setLoading(true)
    setError(null)
    const fields: Record<string, string> = mappingOverride
      ? { mapping: JSON.stringify(mappingOverride) }
      : {}
    apiPost<MetricsResult>('/metrics', buildDatasetForm(file, storagePath, fields))
      .then(setMetrics)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'No se pudieron calcular las métricas.'),
      )
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, cleaning, datasetId, storagePath, uploadedAt, metrics, setMetrics])

  return { ready, metrics, loading, error }
}
