import { describe, expect, it } from 'vitest'
import {
  chartColorForKey,
  distributionChartKind,
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

  it('mantiene el color de una dimensión aunque cambie el orden de los datos', () => {
    expect(chartColorForKey('Estado Pago')).toBe(chartColorForKey('Estado Pago'))
    expect(chartColorForKey('Estado Pago', 1)).not.toBe(chartColorForKey('Estado Pago'))
  })

  it('usa donut solo para composiciones pequeñas no negativas', () => {
    expect(distributionChartKind([{ registros: 8 }, { registros: 2 }])).toBe('donut')
    expect(distributionChartKind(Array.from({ length: 8 }, () => ({ registros: 1 })))).toBe('bars')
    expect(distributionChartKind([{ registros: 8 }, { registros: -2 }])).toBe('bars')
  })
})
