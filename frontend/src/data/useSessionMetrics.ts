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
  const {
    file, cleaning, datasetId, storagePath, uploadedAt, metrics, setMetrics,
    mappingOverride, sheet, eliminarDuplicados,
  } = useDataset()
  const ready = Boolean(file && cleaning)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fetchedFor = useRef<string | null>(null)
  const latestRequest = useRef(0)

  useEffect(() => {
    if (!file || !cleaning) return
    const datasetKey = datasetId ?? storagePath ?? String(uploadedAt?.getTime() ?? 0)
    // Hoja y mapeo en la clave: si el usuario los cambia, se recalcula (Fase 11)
    const key = `${datasetKey}|${sheet ?? ''}|${JSON.stringify(mappingOverride ?? {})}|${eliminarDuplicados}`
    if (metrics && isFullPeriod(metrics)) {
      fetchedFor.current = key
      setActiveCurrency(metrics.moneda)
      return
    }
    fetchedFor.current = key
    const controller = new AbortController()
    const requestId = latestRequest.current + 1
    latestRequest.current = requestId
    setLoading(true)
    setError(null)
    const fields: Record<string, string> = {
      eliminar_duplicados: String(eliminarDuplicados),
      ...(mappingOverride ? { mapping: JSON.stringify(mappingOverride) } : {}),
      ...(sheet ? { sheet } : {}),
    }
    apiPost<MetricsResult>('/metrics', buildDatasetForm(file, storagePath, fields), {
      signal: controller.signal,
    })
      .then((result) => {
        if (latestRequest.current !== requestId || controller.signal.aborted) return
        setActiveCurrency(result.moneda)
        setMetrics(result)
      })
      .catch((err) => {
        if (latestRequest.current !== requestId || controller.signal.aborted) return
        // Sin este reset, el hook nunca volvería a intentar tras un fallo
        fetchedFor.current = null
        setError(err instanceof ApiError ? err.message : 'No se pudieron calcular las métricas.')
      })
      .finally(() => {
        if (latestRequest.current === requestId && !controller.signal.aborted) setLoading(false)
      })
    return () => {
      controller.abort()
      // Fase 12b: liberar la clave al abortar (StrictMode/remontaje) — si
      // queda "ya pedida" con la petición abortada, Alertas/Reportes no cargan.
      if (fetchedFor.current === key) fetchedFor.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, cleaning, datasetId, storagePath, uploadedAt, metrics, setMetrics, sheet, mappingOverride, eliminarDuplicados])

  // Solo entregar métricas del periodo completo (nunca el mes filtrado ajeno).
  return { ready, metrics: isFullPeriod(metrics) ? metrics : null, loading, error }
}
