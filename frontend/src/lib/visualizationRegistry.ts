export type VisualizationConfidence = 'certified' | 'partial' | 'estimated'

export interface VisualizationDefinition {
  id: string
  family: 'trend' | 'comparison' | 'composition' | 'distribution' | 'matrix' | 'relationship'
  requiredInputs: string[]
  optionalInputs: string[]
  metric: string
  granularity: string
  unit: string
  priority: number
  fallback: string | null
}

/** Registro semántico de las visualizaciones adaptativas del resumen. */
export const SUMMARY_VISUALIZATION_REGISTRY: readonly VisualizationDefinition[] = [
  { id: 'sales-channel', family: 'comparison', requiredInputs: ['monto', 'canal|sucursal'], optionalInputs: ['periodo'], metric: 'ventas_netas', granularity: 'categoria', unit: 'currency', priority: 95, fallback: null },
  { id: 'sales-product-pareto', family: 'composition', requiredInputs: ['monto', 'producto|servicio'], optionalInputs: ['costo'], metric: 'ventas_netas', granularity: 'producto', unit: 'currency', priority: 92, fallback: 'ranked-bars' },
  { id: 'sales-month-dimension', family: 'matrix', requiredInputs: ['monto', 'fecha', 'dimension'], optionalInputs: [], metric: 'ventas_netas', granularity: 'mes-categoria', unit: 'currency|percent', priority: 88, fallback: 'sales-dimension' },
  { id: 'sales-flexible', family: 'comparison', requiredInputs: ['monto', 'dimension'], optionalInputs: [], metric: 'ventas_netas', granularity: 'categoria', unit: 'currency', priority: 75, fallback: 'stacked-100' },
  { id: 'sales-client-pareto', family: 'composition', requiredInputs: ['monto', 'cliente'], optionalInputs: ['costo'], metric: 'ventas_netas', granularity: 'cliente', unit: 'currency', priority: 84, fallback: 'ranked-bars' },
  { id: 'sales-weekday', family: 'comparison', requiredInputs: ['monto', 'fecha'], optionalInputs: [], metric: 'ventas_netas', granularity: 'dia-semana', unit: 'currency', priority: 80, fallback: null },
  { id: 'sales-distribution', family: 'distribution', requiredInputs: ['monto'], optionalInputs: ['documento'], metric: 'ventas_netas', granularity: 'linea|registro', unit: 'count', priority: 78, fallback: 'summary-statistics' },
] as const

export const MAX_SUMMARY_CHARTS = 8

const DIMENSION_ALIASES: Array<[RegExp, string]> = [
  [/\b(?:dcto|descuento|discount)\b/, 'descuento'],
  [/\b(?:estado|status)\b/, 'estado'],
  [/\b(?:medio|metodo|forma)\s+(?:de\s+)?pago\b/, 'metodo-pago'],
  [/\b(?:sucursal|tienda|local|branch)\b/, 'sucursal'],
  [/\b(?:producto|sku|articulo|item|servicio)\b/, 'producto-servicio'],
  [/\b(?:cliente|customer|comprador)\b/, 'cliente'],
]

export function normalizeVisualizationDimension(value: string): string {
  const normalized = value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('es-CL')
    .replace(/[_-]+/g, ' ')
    .replace(/[^a-z0-9% ]+/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return DIMENSION_ALIASES.find(([pattern]) => pattern.test(normalized))?.[1] ?? normalized
}

export function analyticalFingerprint(parts: {
  metric: string
  dimension: string
  granularity: string
  period?: string
  filters?: string
  source?: string
  calculation?: string
}): string {
  return [
    parts.metric,
    normalizeVisualizationDimension(parts.dimension),
    parts.granularity,
    parts.period ?? 'all',
    parts.filters ?? 'all',
    parts.source ?? 'workbook',
    parts.calculation ?? 'observed',
  ].join('|')
}

export function selectUniqueVisualizations<T extends { fingerprint: string; priority: number; coverage?: number; confidence?: VisualizationConfidence }>(
  candidates: T[],
  limit = MAX_SUMMARY_CHARTS,
): { selected: T[]; omitted: number } {
  const confidenceRank: Record<VisualizationConfidence, number> = {
    certified: 3,
    partial: 2,
    estimated: 1,
  }
  const sorted = [...candidates].sort((left, right) => (
    (confidenceRank[right.confidence ?? 'certified'] - confidenceRank[left.confidence ?? 'certified'])
    || ((right.coverage ?? 1) - (left.coverage ?? 1))
    || (right.priority - left.priority)
  ))
  const seen = new Set<string>()
  const unique = sorted.filter((candidate) => {
    if (seen.has(candidate.fingerprint)) return false
    seen.add(candidate.fingerprint)
    return true
  })
  return { selected: unique.slice(0, Math.max(0, limit)), omitted: candidates.length - Math.min(unique.length, Math.max(0, limit)) }
}
