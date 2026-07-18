import type { MetricsResult, RelationshipResult } from './types'

const MAX_METRICS = 24
const MAX_RELATIONSHIPS = 8
const metricsCache = new Map<string, MetricsResult>()
const relationshipCache = new Map<string, RelationshipResult>()
const metricsInFlight = new Map<string, Promise<MetricsResult>>()
let cacheGeneration = 0

function remember<T>(cache: Map<string, T>, key: string, value: T, max: number) {
  cache.delete(key)
  cache.set(key, value)
  while (cache.size > max) {
    const oldest = cache.keys().next().value as string | undefined
    if (oldest === undefined) break
    cache.delete(oldest)
  }
}

export function getCachedMetrics(key: string): MetricsResult | null {
  const value = metricsCache.get(key) ?? null
  if (value) remember(metricsCache, key, value, MAX_METRICS)
  return value
}

export function cacheMetrics(key: string, value: MetricsResult) {
  remember(metricsCache, key, value, MAX_METRICS)
}

export interface MetricsCacheKeyParts {
  dataset: string
  dateFrom?: string | null
  dateTo?: string | null
  sheet?: string | null
  analysisScope?: unknown
  mapping?: unknown
  eliminarDuplicados: boolean
  revision?: number | null
  rules?: unknown
  directed?: unknown
  manifest?: unknown
  retry?: number
}

/** Una clave compartida evita que Resumen, Explorar, Reportes y la IA
 * describan el mismo procesamiento con formatos distintos. */
export function metricsCacheKey(parts: MetricsCacheKeyParts): string {
  return JSON.stringify({
    dataset: parts.dataset,
    dateFrom: parts.dateFrom ?? '',
    dateTo: parts.dateTo ?? '',
    sheet: parts.sheet ?? '',
    analysisScope: parts.analysisScope ?? null,
    mapping: parts.mapping ?? null,
    eliminarDuplicados: parts.eliminarDuplicados,
    revision: parts.revision ?? null,
    rules: parts.rules ?? null,
    directed: parts.directed ?? null,
    manifest: parts.manifest ?? null,
    retry: parts.retry ?? 0,
  })
}

/** Reutiliza tanto una respuesta terminada como una petición en curso.
 * La petición compartida no pertenece al ciclo de vida de una sola pantalla:
 * cada consumidor puede ignorar el resultado al desmontarse sin cancelar el
 * trabajo que otra pantalla (por ejemplo el panel IA) sigue esperando. */
export function requestMetrics(
  key: string,
  producer: () => Promise<MetricsResult>,
): Promise<MetricsResult> {
  const cached = getCachedMetrics(key)
  if (cached) return Promise.resolve(cached)
  const pending = metricsInFlight.get(key)
  if (pending) return pending
  const generation = cacheGeneration
  let request: Promise<MetricsResult>
  request = producer()
    .then((value) => {
      if (generation === cacheGeneration) cacheMetrics(key, value)
      return value
    })
    .finally(() => {
      if (metricsInFlight.get(key) === request) metricsInFlight.delete(key)
    })
  metricsInFlight.set(key, request)
  return request
}

export function getCachedRelationships(key: string): RelationshipResult | null {
  const value = relationshipCache.get(key) ?? null
  if (value) remember(relationshipCache, key, value, MAX_RELATIONSHIPS)
  return value
}

export function cacheRelationships(key: string, value: RelationshipResult) {
  remember(relationshipCache, key, value, MAX_RELATIONSHIPS)
}

export function clearAnalysisCaches() {
  cacheGeneration += 1
  metricsCache.clear()
  relationshipCache.clear()
  metricsInFlight.clear()
}
