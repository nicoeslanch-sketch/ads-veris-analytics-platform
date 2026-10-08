import { describe, expect, it } from 'vitest'
import { hasAssistantMetricFilters, initialMetricSuggestions } from './AiPanel'
import type { MetricsResult } from '../../lib/types'

describe('hasAssistantMetricFilters', () => {
  it('reuses the global snapshot only for the unfiltered dashboard', () => {
    expect(hasAssistantMetricFilters({ from: null, to: null }, {})).toBe(false)
  })

  it('requires visible metrics for dates or business filters', () => {
    expect(hasAssistantMetricFilters({ from: '2026-05-01', to: '2026-05-31' }, {})).toBe(true)
    expect(hasAssistantMetricFilters({ from: null, to: null }, { equipo: 'FLUJO' })).toBe(true)
  })
})

describe('initialMetricSuggestions', () => {
  it.each([
    { tipo_analisis: 'catalogo_productos' },
    { analisis_productos: { productos: 3 } },
  ])('keeps catalog prompts distinct from sales: %j', (catalog) => {
    const metrics = { ...catalog, kpis: { ingresos_totales: { valor: 0 } } } as Partial<MetricsResult>
    expect(initialMetricSuggestions(metrics)).toEqual([
      '¿Cuántos productos hay en mi catálogo?',
      '¿Cuál es el costo promedio del catálogo?',
      '¿Cuál es el margen potencial del catálogo?',
      '¿Qué problemas de calidad debo revisar?',
    ])
  })

  it('does not suggest sales for an operational sheet', () => {
    const metrics: Partial<MetricsResult> = { analisis_generico: {
      registros: 3, columnas: 2, celdas_informadas_pct: 100, columnas_disponibles: [],
    } }
    expect(initialMetricSuggestions(metrics).join(' ')).not.toContain('ingresos')
    expect(initialMetricSuggestions(metrics)[0]).toContain('resumen')
  })

  it('keeps inventory prompts grounded in stock', () => {
    const metrics = { analisis_inventario: {} } as Partial<MetricsResult>
    expect(initialMetricSuggestions(metrics)[0]).toContain('stock')
  })
})
