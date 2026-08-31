import type { CleanResult, StandardizeResult } from './types'

export interface DatasetWorkbookSummary {
  rows: number
  columns: number
  quality?: number
  status: 'estandarizado' | 'limpio'
}

export function summarizeStandardizedWorkbook(
  results: StandardizeResult[],
): DatasetWorkbookSummary | null {
  if (results.length === 0) return null
  return {
    rows: results.reduce((total, result) => total + result.filas, 0),
    columns: results.reduce((total, result) => total + result.columnas, 0),
    status: 'estandarizado',
  }
}

export function summarizeCleanWorkbook(
  results: CleanResult[],
): DatasetWorkbookSummary | null {
  if (results.length === 0) return null
  const rows = results.reduce((total, result) => total + result.resumen.filas_despues, 0)
  const qualityWeight = results.reduce(
    (total, result) => total + (
      result.resumen.calidad_despues * Math.max(result.resumen.filas_despues, 1)
    ),
    0,
  )
  const denominator = results.reduce(
    (total, result) => total + Math.max(result.resumen.filas_despues, 1),
    0,
  )
  return {
    rows,
    columns: results.reduce(
      (total, result) => total + result.resumen.columnas_despues,
      0,
    ),
    quality: Math.round((qualityWeight / denominator) * 10) / 10,
    status: 'limpio',
  }
}
