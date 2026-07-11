/** Métricas del dataset de la sesión para páginas que las consumen completas
 * (Alertas, Reportes). Reusa las del contexto SOLO si corresponden al periodo
 * completo; si el Resumen dejó cacheado un mes filtrado, se recalculan — así
 * un reporte jamás hereda en silencio el mes que estaba mirando el usuario
 * (Fase 10 §5). */

import { useEffect, useRef, useState } from 'react'
import { ApiError, apiPost, buildDatasetForm } from '../lib/api'
import { setActiveCurrency } from '../lib/format'
import type { MetricsResult } from '../lib/types'
import { useDataset } from './DatasetContext'

function isFullPeriod(m: MetricsResult | null): boolean {
  return m !== null && !m.periodo.desde && !m.periodo.hasta
}

export function useSessionMetrics(): {
  ready: boolean
  metrics: MetricsResult | null
  loading: boolean
  error: string | null
} {
  const { file, cleaning, datasetId, storagePath, uploadedAt, metrics, setMetrics, mappingOverride, sheet } =
    useDataset()
  const ready = Boolean(file && cleaning)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fetchedFor = useRef<string | null>(null)

  useEffect(() => {
    if (!file || !cleaning || isFullPeriod(metrics)) return
    const datasetKey = datasetId ?? storagePath ?? String(uploadedAt?.getTime() ?? 0)
    // Hoja y mapeo en la clave: si el usuario los cambia, se recalcula (Fase 11)
    const key = `${datasetKey}|${sheet ?? ''}|${JSON.stringify(mappingOverride ?? {})}`
    if (fetchedFor.current === key) return
    fetchedFor.current = key
    setLoading(true)
    setError(null)
    const fields: Record<string, string> = {
      ...(mappingOverride ? { mapping: JSON.stringify(mappingOverride) } : {}),
      ...(sheet ? { sheet } : {}),
    }
    apiPost<MetricsResult>('/metrics', buildDatasetForm(file, storagePath, fields))
      .then((result) => {
        setActiveCurrency(result.moneda)
        setMetrics(result)
      })
      .catch((err) => {
        // Sin este reset, el hook nunca volvería a intentar tras un fallo
        fetchedFor.current = null
        setError(err instanceof ApiError ? err.message : 'No se pudieron calcular las métricas.')
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, cleaning, datasetId, storagePath, uploadedAt, metrics, setMetrics, sheet, mappingOverride])

  // Solo entregar métricas del periodo completo (nunca el mes filtrado ajeno).
  return { ready, metrics: isFullPeriod(metrics) ? metrics : null, loading, error }
}
