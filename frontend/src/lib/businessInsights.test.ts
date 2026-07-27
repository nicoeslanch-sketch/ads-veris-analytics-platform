import { describe, expect, it } from 'vitest'
import { computeBusinessInsights } from './businessInsights'
import type { MetricsResult } from './types'

/** Base mínima y neutra: sin señales, no debe producir ninguna lectura. Cada
 * test enciende SOLO la condición que quiere comprobar. */
function baseMetrics(overrides: Partial<MetricsResult> = {}): MetricsResult {
  return {
    kpis: {
      ingresos_totales: { valor: 1_000_000, variacion_pct: null },
      ticket_promedio: 1000,
      transacciones: 1000,
    },
    evolucion_mensual: [],
    advertencias: [],
    ...overrides,
  } as unknown as MetricsResult
}

const ids = (m: MetricsResult) => computeBusinessInsights(m).map((insight) => insight.id)

describe('computeBusinessInsights', () => {
  it('no inventa lecturas cuando no hay señales', () => {
    expect(computeBusinessInsights(baseMetrics())).toEqual([])
  })

  it('detecta que los costos superan a los ingresos', () => {
    const result = computeBusinessInsights(baseMetrics({
      kpis: {
        ingresos_totales: { valor: 1_000_000, variacion_pct: null },
        ticket_promedio: 1000,
        transacciones: 1000,
        margen_utilidad_pct: { valor: -12, variacion_puntos: null },
      },
    } as Partial<MetricsResult>))
    const insight = result.find((item) => item.id === 'margen-negativo')
    expect(insight).toBeDefined()
    expect(insight?.tone).toBe('riesgo')
    // La lectura debe explicar el negocio, no repetir la cifra.
    expect(insight?.significado).toMatch(/cuesta más de lo que te deja/i)
    expect(insight?.accion).toBeTruthy()
  })

  it('señala una categoría con margen negativo y sugiere reinvertir', () => {
    const result = computeBusinessInsights(baseMetrics({
      por_categoria: [
        { nombre: 'Aseo', ingresos: 400_000, porcentaje: 40, margen_pct: -8 },
        { nombre: 'Oficina', ingresos: 600_000, porcentaje: 60, margen_pct: 30 },
      ],
    } as Partial<MetricsResult>))
    const insight = result.find((item) => item.id === 'categoria-perdida')
    expect(insight?.titulo).toContain('Aseo')
    expect(insight?.accion).toMatch(/reinvertir|descontinuar/i)
  })

  it('avisa de dependencia de un solo producto', () => {
    const result = computeBusinessInsights(baseMetrics({
      top_productos: [
        { nombre: 'Tóner MaxPro', ingresos: 400_000, porcentaje: 40, participacion_bruta_pct: 40 },
      ],
    } as Partial<MetricsResult>))
    expect(ids(baseMetrics())).not.toContain('concentracion-producto')
    expect(result.find((item) => item.id === 'concentracion-producto')?.titulo).toContain('Tóner MaxPro')
  })

  it('explica la caída del mes apuntando a dónde mirar', () => {
    const result = computeBusinessInsights(baseMetrics({
      evolucion_mensual: [
        { mes: '2026-01', ingresos: 1_000_000 },
        { mes: '2026-02', ingresos: 700_000 },
      ],
      por_categoria: [{ nombre: 'Ferretería', ingresos: 500_000, porcentaje: 50, participacion_bruta_pct: 50 }],
    } as Partial<MetricsResult>))
    const insight = result.find((item) => item.id === 'cambio-mes')
    expect(insight?.tone).toBe('riesgo')
    expect(insight?.titulo).toMatch(/cayeron/i)
    expect(insight?.accion).toContain('Ferretería')
  })

  it('no marca un cambio de mes irrelevante', () => {
    const result = computeBusinessInsights(baseMetrics({
      evolucion_mensual: [
        { mes: '2026-01', ingresos: 1_000_000 },
        { mes: '2026-02', ingresos: 1_020_000 },
      ],
    } as Partial<MetricsResult>))
    expect(result.map((item) => item.id)).not.toContain('cambio-mes')
  })

  it('detecta devoluciones que se comen la venta', () => {
    const result = computeBusinessInsights(baseMetrics({
      kpis: {
        ingresos_totales: { valor: 1_000_000, variacion_pct: null },
        ticket_promedio: 1000,
        transacciones: 1000,
        devoluciones: { monto: -150_000, filas: 40 },
      },
    } as Partial<MetricsResult>))
    expect(result.map((item) => item.id)).toContain('devoluciones-altas')
  })

  it('toda lectura trae significado, acción y evidencia', () => {
    const result = computeBusinessInsights(baseMetrics({
      kpis: {
        ingresos_totales: { valor: 1_000_000, variacion_pct: null },
        ticket_promedio: 1000,
        transacciones: 1000,
        margen_utilidad_pct: { valor: -5, variacion_puntos: null },
        devoluciones: { monto: -200_000, filas: 10 },
      },
      por_categoria: [{ nombre: 'X', ingresos: 100, porcentaje: 100, margen_pct: -3 }],
    } as Partial<MetricsResult>))
    expect(result.length).toBeGreaterThan(0)
    for (const insight of result) {
      expect(insight.titulo.length).toBeGreaterThan(0)
      expect(insight.significado.length).toBeGreaterThan(0)
      expect(insight.accion.length).toBeGreaterThan(0)
      expect(insight.evidencia.length).toBeGreaterThan(0)
    }
  })
})
