import { describe, expect, it } from 'vitest'
import {
  analyticalFingerprint,
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
})
