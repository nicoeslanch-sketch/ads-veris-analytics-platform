import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import AdaptiveProfileSummary from './AdaptiveProfileSummary'
import type { MetricsResult } from '../lib/types'

describe('inventory minimum coverage', () => {
  it('does not claim sufficient stock or show a zero-shortage chart without minimums', () => {
    const metrics: MetricsResult = {
      archivo: 'inventario.xlsx', calidad_datos: 100, moneda: 'CLP', mapeo: {},
      agrupado_por_canal: null, periodo: { desde: null, hasta: null, meses_disponibles: [] },
      kpis: { ingresos_totales: null, transacciones: 0, ticket_promedio: null,
        gastos_totales: null, ganancia_neta: null, margen_utilidad_pct: null, flujo_caja: null },
      evolucion_mensual: [], proyeccion: null, advertencias: [],
      indicadores_financieros: { disponible: false, nota: '', items: {} },
      analisis_inventario: {
      registros: 2, productos: 1, stock_total: 7, stock_minimo_total: 0,
      bajo_minimo: 0, minimos_disponibles: false, cobertura_stock_pct: 100,
      sucursales: [], columna_actualizacion: null, por_sucursal: [
        { nombre: 'A', registros: 1, stock: 3, bajo_minimo: 0, stocks_negativos: 0 },
        { nombre: 'B', registros: 1, stock: 4, bajo_minimo: 0, stocks_negativos: 0 },
      ],
    } }
    const html = renderToStaticMarkup(createElement(AdaptiveProfileSummary, { metrics, variant: 'explore' }))
    expect(html).toContain('No disponible')
    expect(html).not.toContain('El stock cubre')
    expect(html).not.toContain('Quiebres por sucursal')
  })
})
