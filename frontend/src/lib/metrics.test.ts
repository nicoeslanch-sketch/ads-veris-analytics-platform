import { describe, expect, it } from 'vitest'
import { principalPorParticipacionBruta, summaryContentKind } from './metrics'
import type { GroupRow, MetricsResult } from './types'

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

  it('prioriza el bloqueo monetario sobre perfiles de productos o campañas', () => {
    const metrics: MetricsResult = {
      archivo: 'mixto.xlsx',
      calidad_datos: 100,
      moneda: 'CLP',
      moneda_mixta: true,
      mapeo: {},
      agrupado_por_canal: null,
      periodo: { desde: null, hasta: null, meses_disponibles: [] },
      kpis: {
        ingresos_totales: null,
        transacciones: 2,
        ticket_promedio: null,
        gastos_totales: null,
        ganancia_neta: null,
        margen_utilidad_pct: null,
        flujo_caja: null,
      },
      evolucion_mensual: [],
      proyeccion: null,
      indicadores_financieros: { disponible: false, nota: '', items: {} },
      advertencias: [],
      analisis_campanas: {
        campanas: 2,
        inversion: null,
        impresiones: 100,
        clics: 10,
        ctr_pct: 10,
        cpc: null,
        plataformas: [],
        estados: [],
      },
    }
    expect(summaryContentKind(metrics)).toBe('mixed_currency')
  })
})
