/** Regla transversal de meses parciales (Fase 14b).
 *
 * Un mes con cobertura parcial jamás compite ni se compara contra meses
 * completos — Alertas, Resumen y Explorar consumen este helper único.
 */
import { describe, expect, it } from 'vitest'
import { mesParcialDe, soloMesesCompletos } from './partial'

const evo = [
  { mes: '2026-04', ingresos: 30000, parcial: false },
  { mes: '2026-05', ingresos: 37200, parcial: false },
  { mes: '2026-06', ingresos: 15000, parcial: true },
]

describe('soloMesesCompletos', () => {
  it('excluye el mes parcial', () => {
    expect(soloMesesCompletos(evo).map((m) => m.mes)).toEqual(['2026-04', '2026-05'])
  })

  it('sin marca de parcialidad (backend antiguo) conserva toda la serie', () => {
    const legacy: Array<{ mes: string; ingresos: number; parcial?: boolean }> = [
      { mes: '2026-04', ingresos: 1 },
      { mes: '2026-05', ingresos: 2 },
    ]
    expect(soloMesesCompletos(legacy)).toHaveLength(2)
  })

  it('el último mes COMPLETO define la variación, no el parcial', () => {
    const completos = soloMesesCompletos(evo)
    const last = completos[completos.length - 1]
    const prev = completos[completos.length - 2]
    const pct = ((last.ingresos - prev.ingresos) / prev.ingresos) * 100
    expect(Math.round(pct)).toBe(24) // abr→may +24%, jamás la "caída" de junio
  })
})

describe('mesParcialDe', () => {
  it('encuentra el mes parcial', () => {
    expect(mesParcialDe(evo)?.mes).toBe('2026-06')
  })
  it('null cuando todos son completos', () => {
    expect(mesParcialDe(evo.slice(0, 2))).toBeNull()
  })
})
