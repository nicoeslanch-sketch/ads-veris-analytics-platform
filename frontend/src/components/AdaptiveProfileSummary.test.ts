import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import AdaptiveProfileSummary from './AdaptiveProfileSummary'
import type { MetricsResult } from '../lib/types'

describe('inventory minimum coverage', () => {
  it('does not claim sufficient stock or show a zero-shortage chart without minimums', () => {
    const metrics = { analisis_inventario: {
      registros: 2, productos: 1, stock_total: 7, stock_minimo_total: 0,
      bajo_minimo: 0, minimos_disponibles: false, cobertura_stock_pct: 100,
      sucursales: [], por_sucursal: [
        { nombre: 'A', registros: 1, stock: 3, bajo_minimo: 0 },
        { nombre: 'B', registros: 1, stock: 4, bajo_minimo: 0 },
      ],
    } } as MetricsResult
    const html = renderToStaticMarkup(createElement(AdaptiveProfileSummary, { metrics, variant: 'explore' }))
    expect(html).toContain('No disponible')
    expect(html).not.toContain('El stock cubre')
    expect(html).not.toContain('Quiebres por sucursal')
  })
})
