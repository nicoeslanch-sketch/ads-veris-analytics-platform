import { describe, expect, it } from 'vitest'
import {
  ACTIVITY_RETENTION_DAYS,
  RECENT_ACTIVITY_LIMIT,
  activityRetentionCutoff,
  hasVerifiedMonetaryIntegrity,
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
  it('calcula un corte estable de 30 días', () => {
    expect(activityRetentionCutoff(new Date('2026-07-25T12:00:00.000Z'))).toBe(
      '2026-06-25T12:00:00.000Z',
    )
    expect(ACTIVITY_RETENTION_DAYS).toBe(30)
  })

  it('mantiene compacta la lista visible', () => {
    expect(RECENT_ACTIVITY_LIMIT).toBe(20)
  })
})
