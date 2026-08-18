import type { MetricsResult, RelationshipResult } from './types'
import { clearSessionAnalysis, readSessionAnalysis, writeSessionAnalysis } from './sessionAnalysisCache'
import { stableSerialize } from './stableSerialize'

const MAX_METRICS = 24
const MAX_RELATIONSHIPS = 8
const metricsCache = new Map<string, MetricsResult>()
const relationshipCache = new Map<string, RelationshipResult>()

interface InFlightMetrics {
  promise: Promise<MetricsResult>
  controller: AbortController
  consumers: Set<AbortSignal>
}

const metricsInFlight = new Map<string, InFlightMetrics>()
const relationshipsInFlight = new Map<string, Promise<RelationshipResult>>()
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
  const value = metricsCache.get(key) ?? readSessionAnalysis<MetricsResult>('metrics', key)
  if (value) remember(metricsCache, key, value, MAX_METRICS)
  return value
}

export function cacheMetrics(key: string, value: MetricsResult) {
  remember(metricsCache, key, value, MAX_METRICS)
  writeSessionAnalysis('metrics', key, value, 12)
}

export interface MetricsCacheKeyParts {
  dataset: string
  dateFrom?: string | null
  dateTo?: string | null
  sheet?: string | null
  analysisScope?: unknown
  businessFilters?: unknown
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
  return stableSerialize({
    dataset: parts.dataset,
    dateFrom: parts.dateFrom ?? '',
    dateTo: parts.dateTo ?? '',
    sheet: parts.sheet ?? '',
    analysisScope: parts.analysisScope ?? null,
    businessFilters: parts.businessFilters ?? null,
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
 * Cada pantalla puede dejar de esperar el resultado sin cancelar el cálculo:
 * así, volver a una vista adopta el trabajo iniciado o su respuesta cacheada. */
function subscribeConsumer(entry: InFlightMetrics, signal?: AbortSignal) {
  if (!signal || signal.aborted) return
  entry.consumers.add(signal)
  const release = () => entry.consumers.delete(signal)
  signal.addEventListener('abort', release, { once: true })
  void entry.promise.then(
    () => signal.removeEventListener('abort', release),
    () => signal.removeEventListener('abort', release),
  )
}

export function requestMetrics(
  key: string,
  producer: (signal: AbortSignal) => Promise<MetricsResult>,
  consumerSignal?: AbortSignal,
): Promise<MetricsResult> {
  const cached = getCachedMetrics(key)
  if (cached) return Promise.resolve(cached)
  const pending = metricsInFlight.get(key)
  if (pending) {
    subscribeConsumer(pending, consumerSignal)
    return pending.promise
  }
  const generation = cacheGeneration
  const controller = new AbortController()
  const entry: InFlightMetrics = {
    promise: Promise.resolve(null as unknown as MetricsResult),
    controller,
    consumers: new Set(),
  }
  const request = producer(controller.signal)
    .then((value) => {
      if (generation === cacheGeneration) cacheMetrics(key, value)
      return value
    })
    .finally(() => {
      if (metricsInFlight.get(key) === entry) metricsInFlight.delete(key)
    })
  entry.promise = request
  metricsInFlight.set(key, entry)
  subscribeConsumer(entry, consumerSignal)
  return request
}

/** Cancela el trabajo compartido solo ante una acción explícita del usuario. */
export function cancelMetricsRequest(key: string) {
  metricsInFlight.get(key)?.controller.abort()
}

export function getCachedRelationships(key: string): RelationshipResult | null {
  const value = relationshipCache.get(key)
    ?? readSessionAnalysis<RelationshipResult>('relationships', key)
  if (value) remember(relationshipCache, key, value, MAX_RELATIONSHIPS)
  return value
}

export function cacheRelationships(key: string, value: RelationshipResult) {
  remember(relationshipCache, key, value, MAX_RELATIONSHIPS)
  writeSessionAnalysis('relationships', key, value, 8)
}

export function requestRelationships(
  key: string,
  producer: () => Promise<RelationshipResult>,
): Promise<RelationshipResult> {
  const cached = getCachedRelationships(key)
  if (cached) return Promise.resolve(cached)
  const pending = relationshipsInFlight.get(key)
  if (pending) return pending
  const generation = cacheGeneration
  const request = producer()
    .then((value) => {
      if (generation === cacheGeneration) cacheRelationships(key, value)
      return value
    })
    .finally(() => {
      if (relationshipsInFlight.get(key) === request) relationshipsInFlight.delete(key)
    })
  relationshipsInFlight.set(key, request)
  return request
}

function clearRuntimeCaches() {
  cacheGeneration += 1
  for (const entry of metricsInFlight.values()) entry.controller.abort()
  metricsCache.clear()
  relationshipCache.clear()
  metricsInFlight.clear()
  relationshipsInFlight.clear()
}

/** Al restaurar el mismo dataset tras una recarga se limpian promesas y RAM,
 * pero se conservan los resultados terminados de esta pestaña. */
export function clearAnalysisRuntimeCaches() {
  clearRuntimeCaches()
}

export function clearAnalysisCaches() {
  clearRuntimeCaches()
  clearSessionAnalysis(['metrics', 'relationships'])
}
