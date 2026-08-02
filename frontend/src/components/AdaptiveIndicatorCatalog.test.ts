import { describe, expect, it } from 'vitest'
import { compactContributionRows } from './AdaptiveIndicatorCatalog'
import type { BusinessGroupRow } from '../lib/types'

function row(nombre: string, ingresos: number): BusinessGroupRow {
  return {
    nombre,
    ingresos,
    ingresos_positivos: ingresos,
    participacion_pct: null,
    costo: ingresos * 0.7,
    utilidad: ingresos * 0.3,
    margen_pct: 30,
    filas: 1,
    filas_pareadas: 1,
    cobertura_costos_pct: 100,
  }
}

describe('compactContributionRows', () => {
  it('mantiene visibles las nueve categorías sin recortar la última', () => {
    const rows = Array.from({ length: 8 }, (_, index) => row(`Categoría ${index + 1}`, 100))
    rows.push(row('Mascotas', 79_686_550))

    const visible = compactContributionRows(rows)

    expect(visible).toHaveLength(9)
    expect(visible[visible.length - 1]?.nombre).toBe('Mascotas')
    expect(visible.reduce((sum, item) => sum + item.ingresos, 0)).toBe(79_687_350)
  })

  it('agrupa el remanente como Otros sin perder ventas ni utilidad', () => {
    const rows = Array.from({ length: 14 }, (_, index) => row(`Categoría ${index + 1}`, index + 1))

    const visible = compactContributionRows(rows, 12)

    expect(visible).toHaveLength(12)
    expect(visible[visible.length - 1]?.nombre).toBe('Otros (3)')
    expect(visible.reduce((sum, item) => sum + item.ingresos, 0)).toBe(105)
    expect(visible.reduce((sum, item) => sum + (item.utilidad ?? 0), 0)).toBeCloseTo(31.5)
  })
})
