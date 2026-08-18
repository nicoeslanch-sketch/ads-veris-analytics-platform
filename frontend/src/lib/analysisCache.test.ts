import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  cacheMetrics,
  cacheRelationships,
  cancelMetricsRequest,
  clearAnalysisCaches,
  clearAnalysisRuntimeCaches,
  getCachedMetrics,
  getCachedRelationships,
  metricsCacheKey,
  requestMetrics,
  requestRelationships,
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

  it('separa la caché cuando cambian los filtros empresariales', () => {
    const base = {
      dataset: 'dataset-1',
      eliminarDuplicados: false,
      revision: 3,
      analysisScope: { mode: 'business', sheets: ['Ventas', 'Productos'] },
    }
    const centro = metricsCacheKey({
      ...base,
      businessFilters: { sucursal: 'Centro' },
    })
    const norte = metricsCacheKey({
      ...base,
      businessFilters: { sucursal: 'Norte' },
    })

    expect(centro).not.toBe(norte)
  })

  it('genera la misma clave aunque el JSON restaurado cambie el orden de propiedades', () => {
    const first = metricsCacheKey({
      dataset: 'dataset-1',
      eliminarDuplicados: false,
      analysisScope: { mode: 'single', sheets: ['Ventas'], active_sheet: 'Ventas' },
      rules: { textos: true, fechas: false },
    })
    const second = metricsCacheKey({
      dataset: 'dataset-1',
      eliminarDuplicados: false,
      analysisScope: { active_sheet: 'Ventas', sheets: ['Ventas'], mode: 'single' },
      rules: { fechas: false, textos: true },
    })
    expect(first).toBe(second)
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

  it('mantiene viva una carga al cambiar de vista y solo la cancela de forma explícita', async () => {
    clearAnalysisCaches()
    const key = metricsCacheKey({
      dataset: 'actual',
      sheet: 'Compras',
      eliminarDuplicados: false,
    })
    const resumen = new AbortController()
    const explorar = new AbortController()
    const sharedSignals: AbortSignal[] = []
    const producer = vi.fn((signal: AbortSignal) => {
      sharedSignals.push(signal)
      return new Promise<MetricsResult>(() => undefined)
    })

    requestMetrics(key, producer, resumen.signal)
    requestMetrics(key, producer, explorar.signal)
    resumen.abort()
    expect(sharedSignals[0]?.aborted).toBe(false)

    explorar.abort()
    expect(sharedSignals[0]?.aborted).toBe(false)

    cancelMetricsRequest(key)
    expect(sharedSignals[0]?.aborted).toBe(true)
    expect(producer).toHaveBeenCalledTimes(1)
  })

  it('comparte la detección de relaciones mientras el usuario cambia de modo', async () => {
    clearAnalysisCaches()
    let resolve!: (value: RelationshipResult) => void
    const producer = vi.fn(() => new Promise<RelationshipResult>((done) => { resolve = done }))
    const first = requestRelationships('dataset|manifest', producer)
    const second = requestRelationships('dataset|manifest', producer)
    expect(first).toBe(second)
    expect(producer).toHaveBeenCalledTimes(1)
    resolve({ candidates: [], safe_count: 0, message: null })
    await first
    expect(getCachedRelationships('dataset|manifest')).not.toBeNull()
  })
})

describe('caché persistente de la pestaña', () => {
  const values = new Map<string, string>()
  const session = {
    get length() { return values.size },
    clear: () => values.clear(),
    getItem: (key: string) => values.get(key) ?? null,
    key: (index: number) => [...values.keys()][index] ?? null,
    removeItem: (key: string) => { values.delete(key) },
    setItem: (key: string, value: string) => { values.set(key, value) },
  } as Storage

  beforeEach(() => {
    values.clear()
    vi.stubGlobal('sessionStorage', session)
    clearAnalysisCaches()
  })

  afterEach(() => {
    clearAnalysisCaches()
    vi.unstubAllGlobals()
  })

  it('restaura métricas después de perder la memoria por una recarga', () => {
    const metrics = metricsFixture()
    cacheMetrics('dataset-restaurado|ventas', metrics)
    clearAnalysisRuntimeCaches()

    expect(getCachedMetrics('dataset-restaurado|ventas')).toEqual(metrics)
  })

  it('el borrado completo elimina también los resultados de la sesión', () => {
    cacheMetrics('dataset-anterior|ventas', metricsFixture())
    clearAnalysisCaches()
    clearAnalysisRuntimeCaches()

    expect(getCachedMetrics('dataset-anterior|ventas')).toBeNull()
  })
})
