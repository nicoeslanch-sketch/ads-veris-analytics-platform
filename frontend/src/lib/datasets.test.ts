import { describe, expect, it } from 'vitest'
import { summarizeCleanWorkbook, summarizeStandardizedWorkbook } from './workbookSummary'
import type { CleanResult, StandardizeResult } from './types'

describe('workbook dataset summaries', () => {
  it('suma las hojas estandarizadas', () => {
    const results = [
      { filas: 100, columnas: 10 },
      { filas: 50, columnas: 5 },
    ] as StandardizeResult[]
    expect(summarizeStandardizedWorkbook(results)).toEqual({
      rows: 150,
      columns: 15,
      status: 'estandarizado',
    })
  })

  it('pondera la calidad por filas y no deja ganar a la ultima hoja', () => {
    const results = [
      { resumen: { filas_despues: 900, columnas_despues: 10, calidad_despues: 90 } },
      { resumen: { filas_despues: 100, columnas_despues: 5, calidad_despues: 100 } },
    ] as CleanResult[]
    expect(summarizeCleanWorkbook(results)).toEqual({
      rows: 1000,
      columns: 15,
      quality: 91,
      status: 'limpio',
    })
  })
})
