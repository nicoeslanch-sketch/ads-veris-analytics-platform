import { describe, expect, it } from 'vitest'
import {
  coverageStateFromDays,
  filterRelationships,
  formatKpiValue,
  isKpiVisible,
  pickRecommended,
  relationshipMatchesQuery,
  sortRelationships,
  templateLabel,
  usableRelationships,
} from './relationshipDashboard'
import { ANALYSIS_MODES, internalModeForLabel } from './analysisModes'
import type { CatalogRelationship } from './types'

function relation(overrides: Partial<CatalogRelationship>): CatalogRelationship {
  return {
    id: overrides.id ?? 'r',
    left_sheet: overrides.left_sheet ?? 'Ventas',
    right_sheet: overrides.right_sheet ?? 'Productos',
    append_sheets: overrides.append_sheets,
    left_keys: overrides.left_keys ?? ['ID_Producto'],
    right_keys: overrides.right_keys ?? ['ID_Producto'],
    type: 'left',
    template: overrides.template ?? 'sales_costs',
    label: overrides.label ?? 'Ventas ↔ Productos',
    purpose: overrides.purpose ?? 'ventas_costos',
    coverage_left: overrides.coverage_left ?? 1,
    coverage_right: overrides.coverage_right ?? 1,
    overlap: overrides.overlap ?? 1,
    cardinality: overrides.cardinality ?? 'muchos_a_uno',
    safe: overrides.safe ?? true,
    recommended: overrides.recommended ?? false,
    source: overrides.source ?? 'automatic',
    currency_compatible: overrides.currency_compatible ?? true,
    reason: overrides.reason ?? null,
  }
}

describe('sortRelationships', () => {
  it('coloca la recomendada primero y no muta la lista', () => {
    const list = [
      relation({ id: 'a', template: 'generic', overlap: 0.9 }),
      relation({ id: 'b', template: 'sales_costs', recommended: true }),
    ]
    const sorted = sortRelationships(list)
    expect(sorted[0].id).toBe('b')
    expect(list[0].id).toBe('a')
  })

  it('ordena por plantilla cuando ninguna es recomendada', () => {
    const sorted = sortRelationships([
      relation({ id: 'inv', template: 'sales_inventory' }),
      relation({ id: 'cost', template: 'sales_costs' }),
    ])
    expect(sorted.map((r) => r.id)).toEqual(['cost', 'inv'])
  })
})

describe('pickRecommended', () => {
  it('prioriza una relación activa válida', () => {
    const list = [
      relation({ id: 'a', recommended: true }),
      relation({ id: 'b', template: 'products_sales' }),
    ]
    expect(pickRecommended(list, 'b')?.id).toBe('b')
  })

  it('cae en la recomendada si no hay activa', () => {
    const list = [
      relation({ id: 'a', template: 'generic' }),
      relation({ id: 'b', recommended: true }),
    ]
    expect(pickRecommended(list)?.id).toBe('b')
  })

  it('devuelve null sin relaciones', () => {
    expect(pickRecommended([])).toBeNull()
  })
})

describe('relationshipMatchesQuery / filterRelationships', () => {
  const list = [
    relation({ id: 'a', left_sheet: 'Ventas', right_sheet: 'Productos', left_keys: ['SKU'] }),
    relation({ id: 'b', left_sheet: 'Ventas', right_sheet: 'Clientes', template: 'sales_customers' }),
  ]
  it('filtra por hoja', () => {
    expect(filterRelationships(list, 'clientes').map((r) => r.id)).toEqual(['b'])
  })
  it('filtra por clave', () => {
    expect(relationshipMatchesQuery(list[0], 'sku')).toBe(true)
    expect(relationshipMatchesQuery(list[1], 'sku')).toBe(false)
  })
  it('encuentra periodos incluidos en una conexión consolidada', () => {
    expect(relationshipMatchesQuery(
      relation({ append_sheets: ['Ventas_2025', 'Ventas_2026'] }),
      '2026',
    )).toBe(true)
  })
  it('query vacía devuelve todo', () => {
    expect(filterRelationships(list, '  ')).toHaveLength(2)
  })
})

describe('usableRelationships', () => {
  it('oculta conexiones inseguras o sin correspondencia real', () => {
    expect(usableRelationships([
      relation({ id: 'ok', safe: true, overlap: 0.82 }),
      relation({ id: 'zero', safe: true, overlap: 0 }),
      relation({ id: 'unsafe', safe: false, overlap: 0.95 }),
    ]).map((item) => item.id)).toEqual(['ok'])
  })
})

describe('coverageStateFromDays', () => {
  it('aplica los umbrales del backend', () => {
    expect(coverageStateFromDays(3)).toBe('critico')
    expect(coverageStateFromDays(10)).toBe('alto')
    expect(coverageStateFromDays(20)).toBe('medio')
    expect(coverageStateFromDays(45)).toBe('sano')
    expect(coverageStateFromDays(null)).toBe('sin_datos')
  })
})

describe('formatKpiValue', () => {
  it('formatea moneda, porcentaje, días y enteros', () => {
    expect(formatKpiValue(12000, 'currency', 'CLP')).toBe('$12.000')
    expect(formatKpiValue(1500, 'currency', 'USD')).toBe('US$1.500')
    expect(formatKpiValue(57.05, 'percent')).toBe('57,1%')
    expect(formatKpiValue(10, 'days')).toBe('10 días')
    expect(formatKpiValue(3, 'integer')).toBe('3')
  })
  it('muestra "No disponible" cuando el valor es null', () => {
    expect(formatKpiValue(null, 'currency')).toBe('No disponible')
  })
})

describe('isKpiVisible', () => {
  it('solo visible con disponible y valor', () => {
    expect(isKpiVisible(true, 10)).toBe(true)
    expect(isKpiVisible(false, 10)).toBe(false)
    expect(isKpiVisible(true, null)).toBe(false)
  })
})

describe('templateLabel', () => {
  it('mapea plantillas conocidas', () => {
    expect(templateLabel('sales_inventory')).toBe('Ventas e inventario')
    expect(templateLabel('generic')).toBe('Relación entre hojas')
  })
})

describe('ANALYSIS_MODES (invariante de los 4 modos)', () => {
  it('conserva textos, orden y modos internos', () => {
    expect(ANALYSIS_MODES.map((entry) => entry.label)).toEqual([
      'Analizar una hoja',
      'Visión del negocio',
      'Unir periodos de venta',
      'Relación manual',
    ])
    expect(ANALYSIS_MODES.map((entry) => entry.mode)).toEqual([
      'single',
      'append_join',
      'append',
      'join',
    ])
  })

  it('mapea cada texto a su modo interno', () => {
    expect(internalModeForLabel('Analizar una hoja')).toBe('single')
    expect(internalModeForLabel('Visión del negocio')).toBe('append_join')
    expect(internalModeForLabel('Unir periodos de venta')).toBe('append')
    expect(internalModeForLabel('Relación manual')).toBe('join')
  })
})
