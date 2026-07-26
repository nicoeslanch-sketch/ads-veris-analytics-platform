import { describe, expect, it } from 'vitest'
import {
  RECENT_ACTIVITY_DATASET_LIMIT,
  RECENT_ACTIVITY_LIMIT,
  compactRecentActivity,
  hasVerifiedMonetaryIntegrity,
  type ActivityRow,
  type AnalysisRow,
} from './history'

function analysis(config: AnalysisRow['config']): AnalysisRow {
  return {
    id: 'analysis-1',
    name: 'Ventas por mes',
    dataset_id: 'dataset-1',
    config,
    findings: ['Ingresos crecieron'],
    recommendation: null,
    created_at: '2026-07-17T00:00:00Z',
  }
}

describe('integridad monetaria de análisis guardados', () => {
  it('bloquea análisis legados sin evidencia', () => {
    expect(hasVerifiedMonetaryIntegrity(analysis({ metrica: 'ingresos' }))).toBe(false)
  })

  it('bloquea cualquier análisis marcado con moneda mixta', () => {
    expect(
      hasVerifiedMonetaryIntegrity(
        analysis({ integridad_monetaria: 'verificada', moneda_mixta: true }),
      ),
    ).toBe(false)
  })

  it('habilita solo el contrato verificado y no mixto', () => {
    expect(
      hasVerifiedMonetaryIntegrity(
        analysis({
          integridad_monetaria: 'verificada',
          moneda_mixta: false,
          moneda: 'CLP',
        }),
      ),
    ).toBe(true)
  })
})

describe('retención de actividad reciente', () => {
  const row = (
    id: string,
    datasetId: string | null,
    activityType: ActivityRow['activity_type'],
    description: string,
  ): ActivityRow => ({
    id,
    dataset_id: datasetId,
    activity_type: activityType,
    description,
    created_at: `2026-07-${String(30 - Number(id)).padStart(2, '0')}T12:00:00Z`,
  })

  it('muestra una sola limpieza por documento aunque existan filas por hoja', () => {
    const compact = compactRecentActivity([
      row('1', 'dataset-a', 'limpieza', 'Limpieza completada: libro.xlsx (Ventas)'),
      row('2', 'dataset-a', 'limpieza', 'Limpieza completada: libro.xlsx (Productos)'),
      row('3', 'dataset-a', 'estandarizacion', 'Estandarización: libro.xlsx'),
    ])
    expect(compact.map((item) => item.id)).toEqual(['1', '3'])
  })

  it('limita por cantidad de fuentes y movimientos, no por días', () => {
    const rows = Array.from({ length: 15 }, (_, index) =>
      row(String(index + 1), `dataset-${index + 1}`, 'carga', `Carga ${index + 1}`),
    )
    const compact = compactRecentActivity(rows, 3, 2)
    expect(compact).toHaveLength(2)
    expect(compact.map((item) => item.dataset_id)).toEqual(['dataset-1', 'dataset-2'])
    expect(RECENT_ACTIVITY_DATASET_LIMIT).toBe(10)
    expect(RECENT_ACTIVITY_LIMIT).toBe(24)
  })
})
