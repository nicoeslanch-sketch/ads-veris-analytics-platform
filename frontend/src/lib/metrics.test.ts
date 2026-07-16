import { describe, expect, it } from 'vitest'
import { principalPorParticipacionBruta } from './metrics'
import type { GroupRow } from './types'

describe('principalPorParticipacionBruta', () => {
  it('no confunde el mayor neto con la mayor concentración bruta', () => {
    const rows: GroupRow[] = [
      {
        nombre: 'B',
        ingresos: 50_000,
        porcentaje: 33.3,
        ventas_brutas: 50_000,
        participacion_bruta_pct: 33.3,
      },
      {
        nombre: 'A',
        ingresos: 10_000,
        porcentaje: 6.7,
        ventas_brutas: 100_000,
        participacion_bruta_pct: 66.7,
      },
    ]

    expect(principalPorParticipacionBruta(rows)?.nombre).toBe('A')
    expect(rows[0].nombre).toBe('B') // la tabla original sigue ordenada por neto
  })

  it('mantiene compatibilidad con respuestas antiguas sin participación bruta', () => {
    const rows: GroupRow[] = [
      { nombre: 'A', ingresos: 10, porcentaje: 20 },
      { nombre: 'B', ingresos: 40, porcentaje: 80 },
    ]
    expect(principalPorParticipacionBruta(rows)?.nombre).toBe('B')
  })
})
