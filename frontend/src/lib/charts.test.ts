import { describe, expect, it } from 'vitest'
import {
  chartColorForKey,
  distributionChartKind,
  buildRobustHeatScale,
  robustHeatIntensity,
  prepareCategoricalChart,
  shouldSplitFinancialScale,
} from './charts'

describe('visualizaciones honestas y estables', () => {
  it('separa escalas cuando costos o utilidad aplastan los ingresos', () => {
    expect(
      shouldSplitFinancialScale([
        { ingresos: 100, gastos: 90, utilidad: 10 },
        { ingresos: 120, gastos: 9_999, utilidad: -9_879 },
      ]),
    ).toBe(true)
    expect(
      shouldSplitFinancialScale([
        { ingresos: 100, gastos: 60, utilidad: 40 },
        { ingresos: 120, gastos: 75, utilidad: 45 },
      ]),
    ).toBe(false)
  })

  it('usa p95 y conserva contraste ante un valor extremo', () => {
    const scale = buildRobustHeatScale([...Array.from({ length: 20 }, (_, index) => index + 1), 10_000])
    expect(scale.reference).toBe(20)
    expect(scale.maximum).toBe(10_000)
    expect(scale.logarithmic).toBe(true)
    expect(robustHeatIntensity(10, scale)).toBeGreaterThan(0.5)
    expect(robustHeatIntensity(10_000, scale)).toBe(1)
  })

  it('mantiene el color de una dimensión aunque cambie el orden de los datos', () => {
    expect(chartColorForKey('Estado Pago')).toBe(chartColorForKey('Estado Pago'))
    expect(chartColorForKey('Estado Pago', 1)).not.toBe(chartColorForKey('Estado Pago'))
  })

  it('usa donut solo para composiciones pequeñas no negativas', () => {
    expect(distributionChartKind([{ registros: 8 }, { registros: 2 }])).toBe('bars')
    expect(distributionChartKind([{ registros: 8 }, { registros: 2 }, { registros: 1 }])).toBe('donut')
    expect(distributionChartKind(Array.from({ length: 8 }, () => ({ registros: 1 })))).toBe('bars')
    expect(distributionChartKind([{ registros: 8 }, { registros: -2 }])).toBe('bars')
  })

  it('elige una barra 100% para dos categorías comparables', () => {
    const concentrated = prepareCategoricalChart([
      { nombre: 'Pagado', ingresos: 93, porcentaje: 93 },
      { nombre: 'Pendiente', ingresos: 7, porcentaje: 7 },
    ])
    expect(concentrated.kind).toBe('concentration')

    const balanced = prepareCategoricalChart([
      { nombre: 'Ventas_S2', ingresos: 52, porcentaje: 52 },
      { nombre: 'Ventas_S1', ingresos: 48, porcentaje: 48 },
    ])
    expect(balanced.kind).toBe('stacked-100')
  })

  it('ordena barras por valor y conserva los rangos en orden natural', () => {
    const branches = prepareCategoricalChart([
      { nombre: 'SUC-04', ingresos: 12 },
      { nombre: 'SUC-01', ingresos: 43 },
      { nombre: 'SUC-03', ingresos: 23 },
      { nombre: 'SUC-02', ingresos: 22 },
    ], { dimension: 'Sucursal' })
    expect(branches.kind).toBe('bars')
    expect(branches.rows.map((row) => row.nombre)).toEqual(['SUC-01', 'SUC-03', 'SUC-02', 'SUC-04'])

    const discounts = prepareCategoricalChart([
      { nombre: '6–10%', ingresos: 35 },
      { nombre: '11–20%', ingresos: 26 },
      { nombre: 'Sin descuento', ingresos: 20 },
      { nombre: '1–5%', ingresos: 19 },
    ], { dimension: 'Dcto %' })
    expect(discounts.kind).toBe('natural-bars')
    expect(discounts.rows.map((row) => row.nombre)).toEqual([
      'Sin descuento', '1–5%', '6–10%', '11–20%',
    ])
  })

  it('agrupa la cola y construye un Pareto que termina en 100%', () => {
    const source = Array.from({ length: 20 }, (_, index) => ({
      nombre: `P${index + 1}`,
      ingresos: 20 - index,
    }))
    const bars = prepareCategoricalChart(source)
    expect(bars.rows).toHaveLength(11)
    expect(bars.rows[bars.rows.length - 1]?.nombre).toBe('Otros (10)')

    const pareto = prepareCategoricalChart(source, { cumulative: true })
    expect(pareto.kind).toBe('pareto')
    expect(pareto.rows[pareto.rows.length - 1]?.acumulado).toBe(100)
  })
})
