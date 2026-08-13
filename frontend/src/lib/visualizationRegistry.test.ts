import { describe, expect, it } from 'vitest'
import {
  analyticalFingerprint,
  isRelevantClientPortfolio,
  normalizeVisualizationDimension,
  selectUniqueVisualizations,
} from './visualizationRegistry'

describe('registro semántico de visualizaciones', () => {
  it('normaliza aliases y produce la misma huella analítica', () => {
    expect(normalizeVisualizationDimension('Dcto %')).toBe('descuento')
    expect(analyticalFingerprint({ metric: 'ventas', dimension: 'Dcto %', granularity: 'categoría' }))
      .toBe(analyticalFingerprint({ metric: 'ventas', dimension: 'Descuento', granularity: 'categoría' }))
  })

  it('elimina preguntas repetidas y respeta el máximo', () => {
    const result = selectUniqueVisualizations([
      { fingerprint: 'ventas|estado', priority: 20, confidence: 'partial' as const },
      { fingerprint: 'ventas|estado', priority: 30, confidence: 'certified' as const },
      { fingerprint: 'ventas|descuento', priority: 10, confidence: 'certified' as const },
    ], 2)
    expect(result.selected.map((item) => item.priority)).toEqual([30, 10])
    expect(result.omitted).toBe(1)
  })

  it('reserva dependencia de cartera para bases concentradas y no clientes masivos', () => {
    expect(isRelevantClientPortfolio({ unicos: 18, concentracion_top_pct: 28, cobertura_identificacion_pct: 96 })).toBe(true)
    expect(isRelevantClientPortfolio({ unicos: 320, concentracion_top_pct: 8, cobertura_identificacion_pct: 100 })).toBe(false)
    expect(isRelevantClientPortfolio({ unicos: 12, concentracion_top_pct: 9, cobertura_identificacion_pct: 100 })).toBe(false)
    expect(isRelevantClientPortfolio({ unicos: 12, concentracion_top_pct: 30, cobertura_identificacion_pct: 55 })).toBe(false)
  })
})
