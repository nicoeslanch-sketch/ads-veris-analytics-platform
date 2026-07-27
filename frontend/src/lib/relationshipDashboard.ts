import { apiPost, buildDatasetForm } from './api'
import { formatNumber } from './format'
import type {
  CatalogRelationship,
  KpiFormat,
  RelationshipCatalog,
  RelationshipDashboard,
  RelationshipResult,
  RelationshipTemplate,
  SheetManifest,
} from './types'

// ── Etiquetas de plantilla (Parte 9) ─────────────────────────────────────────
const TEMPLATE_LABELS: Record<RelationshipTemplate, string> = {
  products_sales: 'Productos y ventas',
  sales_costs: 'Ventas y costos',
  sales_inventory: 'Ventas e inventario',
  sales_customers: 'Ventas y clientes',
  sales_sellers: 'Ventas y vendedores',
  sales_branches: 'Ventas y sucursales',
  purchases_costs: 'Compras y costos',
  expenses_branches: 'Gastos y sucursales',
  generic: 'Relación entre hojas',
}

const TEMPLATE_DESCRIPTIONS: Record<RelationshipTemplate, string> = {
  products_sales: 'Enriquece las ventas con los atributos del catálogo de productos.',
  sales_costs: 'Cruza las ventas con sus costos para calcular utilidad y margen.',
  sales_inventory: 'Relaciona las ventas con el stock para estimar cobertura y riesgo de quiebre.',
  sales_customers: 'Analiza las ventas por cliente identificado.',
  sales_sellers: 'Compara el desempeño de ventas por vendedor.',
  sales_branches: 'Compara el desempeño de ventas por sucursal.',
  purchases_costs: 'Analiza las compras y la evolución de sus costos.',
  expenses_branches: 'Distribuye los gastos por sucursal.',
  generic: 'Muestra la calidad y el comportamiento de la relación entre las hojas.',
}

export function templateLabel(template: RelationshipTemplate): string {
  return TEMPLATE_LABELS[template] ?? TEMPLATE_LABELS.generic
}

export function templateDescription(template: RelationshipTemplate): string {
  return TEMPLATE_DESCRIPTIONS[template] ?? TEMPLATE_DESCRIPTIONS.generic
}

// ── Orden y selección de conexiones (Parte 5) ────────────────────────────────
const TEMPLATE_ORDER: Record<RelationshipTemplate, number> = {
  sales_costs: 0,
  products_sales: 1,
  sales_inventory: 2,
  sales_customers: 3,
  sales_sellers: 4,
  sales_branches: 5,
  purchases_costs: 6,
  expenses_branches: 7,
  generic: 8,
}

/** Ordena por utilidad: recomendada primero, luego por plantilla y solapamiento.
 * Es puro y estable: no muta la lista recibida. */
export function sortRelationships(
  relationships: readonly CatalogRelationship[],
): CatalogRelationship[] {
  return [...relationships].sort((a, b) => {
    if (a.recommended !== b.recommended) return a.recommended ? -1 : 1
    const orderDiff = (TEMPLATE_ORDER[a.template] ?? 9) - (TEMPLATE_ORDER[b.template] ?? 9)
    if (orderDiff !== 0) return orderDiff
    if (b.overlap !== a.overlap) return b.overlap - a.overlap
    return a.label.localeCompare(b.label)
  })
}

/** La relación que debe quedar activa al entrar (Parte 5.4):
 * 1) una relación `join` activa y válida, 2) la recomendada, 3) la de mejor
 * puntuación, 4) nada. */
export function pickRecommended(
  relationships: readonly CatalogRelationship[],
  activeJoinId?: string | null,
): CatalogRelationship | null {
  if (!relationships.length) return null
  const sorted = sortRelationships(relationships)
  if (activeJoinId) {
    const active = sorted.find((relation) => relation.id === activeJoinId && relation.safe)
    if (active) return active
  }
  return sorted.find((relation) => relation.recommended && relation.safe) ?? sorted[0]
}

/** Filtra por hoja, clave o tipo de relación (buscador del panel). Puro. */
export function relationshipMatchesQuery(
  relation: CatalogRelationship,
  rawQuery: string,
): boolean {
  const query = rawQuery.trim().toLowerCase()
  if (!query) return true
  const haystack = [
    relation.left_sheet,
    relation.right_sheet,
    relation.label,
    templateLabel(relation.template),
    ...(relation.append_sheets ?? []),
    ...relation.left_keys,
    ...relation.right_keys,
  ]
    .join(' ')
    .toLowerCase()
  return haystack.includes(query)
}

export function filterRelationships(
  relationships: readonly CatalogRelationship[],
  query: string,
): CatalogRelationship[] {
  return relationships.filter((relation) => relationshipMatchesQuery(relation, query))
}

/** Solo ofrece cruces validados y con correspondencia real. Una relación
 * restaurada con 0% nunca debe aparecer como seleccionable. */
export function usableRelationships(
  relationships: readonly CatalogRelationship[],
): CatalogRelationship[] {
  return relationships.filter((relation) => relation.safe && relation.overlap > 0)
}

// ── Estado de riesgo de cobertura (Parte 8) ──────────────────────────────────
export type CoverageState = 'critico' | 'alto' | 'medio' | 'sano' | 'sin_datos'

export const COVERAGE_STATE_LABELS: Record<CoverageState, string> = {
  critico: 'Crítico',
  alto: 'Alto',
  medio: 'Medio',
  sano: 'Sano',
  sin_datos: 'Sin datos',
}

/** Mismos umbrales que el backend: <7 crítico, <15 alto, <30 medio, ≥30 sano. */
export function coverageStateFromDays(days: number | null | undefined): CoverageState {
  if (days === null || days === undefined || Number.isNaN(days)) return 'sin_datos'
  if (days < 7) return 'critico'
  if (days < 15) return 'alto'
  if (days < 30) return 'medio'
  return 'sano'
}

// ── Formato de valores del contrato ──────────────────────────────────────────
const CURRENCY_PREFIX: Record<string, string> = { CLP: '$', USD: 'US$', EUR: '€' }

export function formatKpiValue(
  value: number | string | null,
  format: KpiFormat,
  currency = 'CLP',
): string {
  if (value === null || value === undefined) return 'No disponible'
  if (typeof value === 'string') return value
  switch (format) {
    case 'currency': {
      const prefix = CURRENCY_PREFIX[currency] ?? '$'
      return `${prefix}${formatNumber(Math.round(value))}`
    }
    case 'percent':
      return `${formatNumber(Math.round(value * 10) / 10)}%`
    case 'days':
      return `${formatNumber(Math.round(value * 10) / 10)} días`
    case 'integer':
      return formatNumber(Math.round(value))
    case 'number':
      return formatNumber(Math.round(value * 100) / 100)
    default:
      return String(value)
  }
}

/** ¿Debe mostrarse el KPI? Solo cuando el backend lo marcó disponible. */
export function isKpiVisible(available: boolean, value: number | string | null): boolean {
  return available && value !== null && value !== undefined
}

// ── Llamadas al backend ──────────────────────────────────────────────────────
export interface RelationshipRequestParams {
  file: File | null
  storagePath: string | null
  datasetId: string | null
  manifest: SheetManifest
}

const catalogCache = new Map<string, RelationshipCatalog>()
const dashboardCache = new Map<string, RelationshipDashboard>()
const MAX_RELATION_CACHE_ENTRIES = 30

export function clearRelationshipDashboardCaches() {
  catalogCache.clear()
  dashboardCache.clear()
}

function requestIdentity(params: RelationshipRequestParams): string {
  const source = params.datasetId
    ?? params.storagePath
    ?? `${params.file?.name ?? ''}:${params.file?.size ?? 0}:${params.file?.lastModified ?? 0}`
  return `${source}|${JSON.stringify(params.manifest)}`
}

function remember<T>(cache: Map<string, T>, key: string, value: T): T {
  cache.set(key, value)
  if (cache.size > MAX_RELATION_CACHE_ENTRIES) {
    const oldest = cache.keys().next().value
    if (oldest) cache.delete(oldest)
  }
  return value
}

export async function fetchRelationshipCatalog(
  params: RelationshipRequestParams,
  signal?: AbortSignal,
): Promise<RelationshipCatalog> {
  const key = requestIdentity(params)
  const cached = catalogCache.get(key)
  if (cached) return cached
  const started = performance.now()
  const result = await apiPost<RelationshipCatalog>(
    '/sheets/relationship-catalog',
    buildDatasetForm(params.file as File, params.storagePath, {
      manifest: JSON.stringify(params.manifest),
      ...(params.datasetId ? { dataset_id: params.datasetId } : {}),
    }),
    // Analizar el libro completo es trabajo de PIPELINE, no una lectura
    // rápida: con el arranque en frío de Render (~50 s) un presupuesto de
    // 60-90 s se agotaba antes de empezar y la petición se cancelaba sola
    // ("La solicitud tardó demasiado"). Sin `timeoutMs` se usa el margen
    // amplio del pipeline, el mismo que ya usa /metrics.
    { signal },
  )
  console.info('[ADS Veris timing] relationship-catalog', {
    durationMs: Math.round(performance.now() - started),
    count: result.relationships.length,
  })
  return remember(catalogCache, key, result)
}

export async function fetchRelationshipDashboard(
  params: RelationshipRequestParams,
  relationship: CatalogRelationship,
  period: { from: string | null; to: string | null },
  signal?: AbortSignal,
): Promise<RelationshipDashboard> {
  const join = {
    left_sheet: relationship.left_sheet,
    right_sheet: relationship.right_sheet,
    left_keys: relationship.left_keys,
    right_keys: relationship.right_keys,
    type: 'left' as const,
    ...(relationship.append_sheets?.length
      ? { append_sheets: relationship.append_sheets }
      : {}),
  }
  const key = `${requestIdentity(params)}|${JSON.stringify(join)}|${period.from ?? ''}|${period.to ?? ''}`
  const cached = dashboardCache.get(key)
  if (cached) return cached
  const started = performance.now()
  const result = await apiPost<RelationshipDashboard>(
    '/sheets/relationship-dashboard',
    buildDatasetForm(params.file as File, params.storagePath, {
      manifest: JSON.stringify(params.manifest),
      relationship: JSON.stringify(join),
      ...(params.datasetId ? { dataset_id: params.datasetId } : {}),
      ...(period.from ? { date_from: period.from } : {}),
      ...(period.to ? { date_to: period.to } : {}),
    }),
    // Analizar el libro completo es trabajo de PIPELINE, no una lectura
    // rápida: con el arranque en frío de Render (~50 s) un presupuesto de
    // 60-90 s se agotaba antes de empezar y la petición se cancelaba sola
    // ("La solicitud tardó demasiado"). Sin `timeoutMs` se usa el margen
    // amplio del pipeline, el mismo que ya usa /metrics.
    { signal },
  )
  console.info('[ADS Veris timing] relationship-dashboard', {
    durationMs: Math.round(performance.now() - started),
    relationship: relationship.id,
  })
  return remember(dashboardCache, key, result)
}

/** Valida una relación manual reutilizando el endpoint existente. Devuelve la
 * candidata evaluada (safe/reason) sin activarla. */
export async function validateManualRelationship(
  params: RelationshipRequestParams,
  join: { left_sheet: string; right_sheet: string; left_keys: string[]; right_keys: string[] },
  signal?: AbortSignal,
): Promise<RelationshipResult> {
  return apiPost<RelationshipResult>(
    '/sheets/relationships',
    buildDatasetForm(params.file as File, params.storagePath, {
      manifest: JSON.stringify(params.manifest),
      relationship: JSON.stringify({ ...join, type: 'left' }),
      ...(params.datasetId ? { dataset_id: params.datasetId } : {}),
    }),
    // Analizar el libro completo es trabajo de PIPELINE, no una lectura
    // rápida: con el arranque en frío de Render (~50 s) un presupuesto de
    // 60-90 s se agotaba antes de empezar y la petición se cancelaba sola
    // ("La solicitud tardó demasiado"). Sin `timeoutMs` se usa el margen
    // amplio del pipeline, el mismo que ya usa /metrics.
    { signal },
  )
}
