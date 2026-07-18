import { describe, expect, it, vi } from 'vitest'
import {
  cacheMetrics,
  cacheRelationships,
  clearAnalysisCaches,
  getCachedMetrics,
  getCachedRelationships,
  metricsCacheKey,
  requestMetrics,
} from './analysisCache'
import type { MetricsResult, RelationshipResult } from './types'

function metricsFixture(): MetricsResult {
  return {
    archivo: 'privado.xlsx',
    calidad_datos: 100,
    moneda: 'CLP',
    mapeo: {},
    agrupado_por_canal: null,
    periodo: { desde: null, hasta: null, meses_disponibles: [] },
    kpis: {
      ingresos_totales: { valor: 1, variacion_pct: null },
      transacciones: 1,
      ticket_promedio: 1,
      gastos_totales: null,
      ganancia_neta: null,
      margen_utilidad_pct: null,
      flujo_caja: null,
    },
    evolucion_mensual: [],
    proyeccion: null,
    indicadores_financieros: { disponible: false, nota: '', items: {} },
    advertencias: [],
  }
}

describe('caché de análisis', () => {
  it('elimina métricas y relaciones al cambiar de dataset o usuario', () => {
    clearAnalysisCaches()
    const metrics = metricsFixture()
    const relationships: RelationshipResult = {
      candidates: [],
      safe_count: 0,
      message: null,
    }
    cacheMetrics('usuario-a|dataset-a', metrics)
    cacheRelationships('usuario-a|dataset-a', relationships)

    expect(getCachedMetrics('usuario-a|dataset-a')).toBe(metrics)
    expect(getCachedRelationships('usuario-a|dataset-a')).toBe(relationships)

    clearAnalysisCaches()
    expect(getCachedMetrics('usuario-a|dataset-a')).toBeNull()
    expect(getCachedRelationships('usuario-a|dataset-a')).toBeNull()
  })

  it('comparte una sola petición para la misma revisión y alcance', async () => {
    clearAnalysisCaches()
    const key = metricsCacheKey({
      dataset: 'dataset-1',
      eliminarDuplicados: false,
      revision: 3,
      rules: { textos: true },
      analysisScope: { mode: 'single', sheets: ['Ventas'] },
    })
    let resolve!: (value: MetricsResult) => void
    const producer = vi.fn(() => new Promise<MetricsResult>((done) => { resolve = done }))

    const first = requestMetrics(key, producer)
    const second = requestMetrics(key, producer)
    expect(first).toBe(second)
    expect(producer).toHaveBeenCalledTimes(1)
    resolve(metricsFixture())
    const resolved = await first
    expect(getCachedMetrics(key)).toBe(resolved)
  })

  it('una petición de una sesión cerrada no repuebla la caché', async () => {
    clearAnalysisCaches()
    const key = metricsCacheKey({ dataset: 'anterior', eliminarDuplicados: false })
    let resolve!: (value: MetricsResult) => void
    const pending = requestMetrics(
      key,
      () => new Promise<MetricsResult>((done) => { resolve = done }),
    )
    clearAnalysisCaches()
    resolve(metricsFixture())
    await pending
    expect(getCachedMetrics(key)).toBeNull()
  })
})
