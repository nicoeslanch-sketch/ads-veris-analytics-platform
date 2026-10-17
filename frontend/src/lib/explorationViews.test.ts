import { describe, expect, it } from 'vitest'
import { buildExplorationViews } from './explorationViews'
import type { ExplorationMeasure } from './explorationAnalysis'
import type { MetricsResult, ProductPatterns, RelationalLedger } from './types'

const measure = (override: Partial<ExplorationMeasure> = {}): ExplorationMeasure => ({ id: 'ingresos', label: 'Ingresos', value: 100, format: 'moneda', formula: '', series: [], dimensions: [], ...override })
const history: ProductPatterns = { meses: ['2024-12', '2025-12'], anos_comparables: ['2024', '2025'], productos_revisados: 1, total_picos: 1, criterio: '', limite: 'Solo datos observados', series: [{ id: '001', nombre: 'Regalo', valores: [{ mes: '2024-12', ventas_netas: 100, ventas_positivas: 100 }, { mes: '2025-12', ventas_netas: 200, ventas_positivas: 200 }] }], picos_recurrentes: [{ id: '001', nombre: 'Regalo', mes: 12, evidencia: [{ ano: '2024', mes: 12, ventas_positivas: 100, participacion_pct: 80 }, { ano: '2025', mes: 12, ventas_positivas: 200, participacion_pct: 85 }] }] }

describe('adaptive exploration chart eligibility', () => {
  it('has no filler charts with empty or unavailable input', () => {
    expect(buildExplorationViews({})).toEqual([])
    expect(buildExplorationViews({ measure: measure() })).toEqual([])
  })
  it('compares matching months across years, preserving missing values', () => {
    const views = buildExplorationViews({ measure: measure({ series: [{ period: '2024-01', value: 10 }, { period: '2025-01', value: 20 }, { period: '2025-02', value: null }, { period: '2024-02', value: 50, partial: true }] }) })
    const chart = views.find(v => v.id === 'year-comparison')!
    expect(chart.rows).toEqual([{ name: 'Ene', '2024': 10, '2025': 20 }])
    expect(views.find(v => v.id === 'monthly-change')).toBeUndefined()
  })
  it('never compares partial bounds or gaps as monthly growth', () => {
    const input = measure({ series: [{ period: '2026-01', value: 10 }, { period: '2026-02', value: 20 }, { period: '2026-04', value: 50 }] })
    expect(buildExplorationViews({ measure: input }).find(v => v.id === 'monthly-change')?.rows).toEqual([{ name: '2026-02', value: 10 }])
    expect(buildExplorationViews({ measure: input, from: '2026-01-15' }).find(v => v.id === 'monthly-change')).toBeUndefined()
  })
  it.each([[-10, 110], [20, 30], [null, 100]])('does not show a false 100%% Pareto for incomplete or signed rankings', (a, b) => {
    const selected = measure({ dimensions: [{ name: 'Producto', groups: [{ name: 'A', value: a }, { name: 'B', value: b }] }] })
    expect(buildExplorationViews({ measure: selected }).find(v => v.id === 'concentration')).toBeUndefined()
  })
  it('reconciles the tail as Other and the cumulative denominator exactly', () => {
    const selected = measure({ dimensions: [{ name: 'Producto', groups: Array.from({ length: 20 }, (_, i) => ({ name: String(i), value: 5 })) }] })
    const chart = buildExplorationViews({ measure: selected }).find(v => v.id === 'concentration')!
    expect(chart.rows).toHaveLength(10)
    expect(chart.rows[9]).toEqual({ name: 'Otros (11)', value: 55, cumulative: 100 })
  })
  it('does not sum rates into a composition', () => {
    const selected = measure({ id: 'ctr', format: 'porcentaje', dimensions: [{ name: 'Campaña', groups: [{ name: 'A', value: 60 }, { name: 'B', value: 40 }] }] })
    expect(buildExplorationViews({ measure: selected })).toEqual([])
  })
  it('keeps missing matrix cells distinct from zero and negative values', () => {
    const selected = measure({ movement: { dimension: 'Sucursal', values: [{ period: '2026-01', name: 'A', value: 0 }, { period: '2026-02', name: 'B', value: -20 }] } })
    const chart = buildExplorationViews({ measure: selected }).find(v => v.id === 'segment-calendar')!
    expect(chart.rows[0]['2026-01']).toBe(0)
    expect(chart.rows[0]['2026-02']).toBeNull()
    expect(chart.rows[1]['2026-02']).toBe(-20)
  })
  it('never manufactures inactivity from product rankings', () => {
    const metrics = { top_productos: [{ nombre: 'A', ingresos: 100 }] } as MetricsResult
    expect(buildExplorationViews({ metrics }).some(v => v.id === 'inactivity')).toBe(false)
  })
  it('requires matching cost coverage before plotting income versus profit', () => {
    const metrics = { tipo_analisis: 'ventas', top_productos: [{ nombre: 'A', ingresos: 100, utilidad: 50, cobertura_costos_pct: 50 }, { nombre: 'B', ingresos: 200, utilidad: 80, cobertura_costos_pct: 100 }] } as MetricsResult
    expect(buildExplorationViews({ metrics }).some(v => v.id === 'sales-profit')).toBe(false)
    metrics.top_productos![0].cobertura_costos_pct = 100
    expect(buildExplorationViews({ metrics }).find(v => v.id === 'sales-profit')?.rows).toEqual([{ name: 'A', x: 100, y: 50 }, { name: 'B', x: 200, y: 80 }])
  })
  it('does not use one sheet as the product history of a legacy business aggregate', () => {
    const metrics = { patrones_productos: history, analisis_negocio: { agrupaciones: {} } } as MetricsResult
    expect(buildExplorationViews({ metrics })).toEqual([])
  })
  it('does not carry old seasonal conclusions into a narrower filter', () => {
    const metrics = { patrones_productos: history } as MetricsResult
    expect(buildExplorationViews({ metrics }).some(v => v.id === 'recurring-peak')).toBe(true)
    const filtered = buildExplorationViews({ metrics, from: '2025-01-01', to: '2025-12-31' })
    expect(filtered.some(v => v.id === 'recurring-peak')).toBe(false)
    expect(filtered.find(v => v.id === 'product-calendar')?.keys).toEqual([{ key: '2025-12', label: '2025-12' }])
  })
  it('supports reconciled multi-sheet periods without reusing estimated sales', () => {
    const ledger: RelationalLedger = { available: true, moneda: 'UF', fuentes: [], advertencias: [], relaciones: [], mensual: [{ mes: '2025-01', ventas: 10, costo: 5, utilidad: 5, unidades: 2 }, { mes: '2026-01', ventas: 20, costo: 12, utilidad: 8, unidades: 4 }], patrones_productos: history, productos: [{ nombre: 'A', ventas: 10, costo: 5, utilidad: 5, unidades: 2 }, { nombre: 'B', ventas: 20, costo: 12, utilidad: 8, unidades: 4 }], kpis: { ventas_netas: 30 } }
    const views = buildExplorationViews({ ledger })
    expect(views.map(v => v.id)).toEqual(expect.arrayContaining(['trend', 'year-comparison', 'product-ranking', 'sales-profit', 'concentration', 'recurring-peak']))
    expect(views.find(v => v.id === 'trend')?.rows[1].ventas).toBe(20)
  })
})
