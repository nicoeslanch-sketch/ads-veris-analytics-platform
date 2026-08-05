/** Paleta de series para gráficos — pasos de las rampas de marca, validados
 * (banda de luminosidad, piso de croma, separación CVD y contraste ≥3:1
 * sobre fondo claro). El navy de marca queda para texto/UI, nunca para datos.
 * Orden categórico FIJO: nunca se recicla ni se reordena por ranking.
 */

export const CHART = {
  ingresos: '#00a3a3', // rampa teal
  gastos: '#a8811c',   // rampa gold (paso oscuro)
  utilidad: '#1f9060', // rampa green
  flujo: '#3d7ec4',    // rampa navy (paso claro)
  alerta: '#d4502b',   // rampa coral (paso oscuro)
} as const

/** Orden categórico fijo para agrupaciones (donut, barras). */
export const CATEGORICAL: string[] = [
  CHART.ingresos,
  CHART.gastos,
  CHART.utilidad,
  CHART.flujo,
  CHART.alerta,
]

/** Un color estable por dimensión. Cambiar de orden o filtrar los datos no
 * cambia la identidad visual del gráfico. */
export function chartColorForKey(key: string, offset = 0): string {
  const hash = Array.from(key).reduce((total, char) => total + char.charCodeAt(0), 0)
  return CATEGORICAL[(hash + offset) % CATEGORICAL.length]
}

/** Evita el gráfico engañoso de una sola escala cuando costos/utilidad son
 * varias veces mayores que los ingresos y dejan la serie de ventas plana. */
export function shouldSplitFinancialScale(
  rows: Array<{ ingresos: number; gastos?: number | null; utilidad?: number | null }>,
  threshold = 4,
): boolean {
  const incomeMax = Math.max(...rows.map((row) => Math.abs(row.ingresos || 0)), 0)
  const resultMax = Math.max(
    ...rows.flatMap((row) => [Math.abs(row.gastos ?? 0), Math.abs(row.utilidad ?? 0)]),
    0,
  )
  return incomeMax > 0 && resultMax / incomeMax >= threshold
}

export function distributionChartKind(
  rows: Array<{ registros: number }>,
): 'donut' | 'bars' {
  return rows.length >= 3 && rows.length <= 5 && rows.every((row) => row.registros >= 0)
    ? 'donut'
    : 'bars'
}

export type CategoricalChartKind =
  | 'concentration'
  | 'stacked-100'
  | 'bars'
  | 'natural-bars'
  | 'pareto'

export interface CategoricalChartSourceRow {
  nombre: string
  ingresos: number
  porcentaje?: number | null
  participacion_neta_pct?: number | null
  participacion_bruta_pct?: number | null
}

export interface PreparedCategoricalRow extends CategoricalChartSourceRow {
  participacion: number
  acumulado: number
  categorias_agrupadas: number
}

export interface PreparedCategoricalChart {
  kind: CategoricalChartKind
  rows: PreparedCategoricalRow[]
  total: number
  totalGroups: number
  groupedCount: number
}

export interface PrepareCategoricalChartOptions {
  dimension?: string
  cumulative?: boolean
  totalGroups?: number
  totalValue?: number
}

const MONTH_ORDER = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]

function normalizedLabel(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('es-CL')
    .replace(/_/g, ' ')
    .trim()
}

/** Detecta dimensiones cuyo orden comunica significado. Nunca deben ordenarse
 * por monto: rangos de descuento/edad y periodos conservan su secuencia. */
export function isNaturalCategoryDimension(dimension = ''): boolean {
  const value = normalizedLabel(dimension)
  return [
    'descuento', 'dcto', 'discount', 'edad', 'age', 'rango',
    'mes', 'month', 'periodo', 'tramo', 'dia de semana', 'weekday',
  ].some((token) => value.includes(token))
}

function naturalCategoryRank(label: string): number {
  const value = normalizedLabel(label)
  const weekday = [
    'lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo',
  ].indexOf(value)
  if (weekday >= 0) return 5_000 + weekday
  if (value === 'sin descuento' || value === 'no discount') return 0
  const isoMonth = value.match(/^(\d{4})[-/]?(\d{2})$/)
  if (isoMonth) return Number(isoMonth[1]) * 12 + Number(isoMonth[2])
  const month = MONTH_ORDER.findIndex((name) => value.startsWith(name.slice(0, 3)))
  if (month >= 0) return 10_000 + month
  const range = value.match(/(-?\d+(?:[.,]\d+)?)\s*(?:%|anos|años)?\s*(?:–|-|a)\s*(-?\d+(?:[.,]\d+)?)/)
  if (range) return 20_000 + Number(range[1].replace(',', '.'))
  const upper = value.match(/^(?:hasta|menor(?:es)? de|<)\s*(\d+(?:[.,]\d+)?)/)
  if (upper) return 19_000 + Number(upper[1].replace(',', '.'))
  const lower = value.match(/^(?:desde|mayor(?:es)? de|>)?\s*(\d+(?:[.,]\d+)?)\s*(?:\+|o mas|o más)/)
  if (lower) return 20_000 + Number(lower[1].replace(',', '.'))
  if (value.includes('sin dato') || value.includes('no informado')) return 90_000
  if (value.includes('fuera de rango')) return 99_000
  return 50_000
}

function explicitShare(row: CategoricalChartSourceRow): number | null {
  const value = row.participacion_neta_pct ?? row.participacion_bruta_pct ?? row.porcentaje
  return value != null && Number.isFinite(value) ? value : null
}

function estimateTotal(
  rows: CategoricalChartSourceRow[],
  requestedTotal?: number,
): number {
  if (requestedTotal != null && Number.isFinite(requestedTotal)) return requestedTotal
  const estimates = rows
    .map((row) => {
      const share = explicitShare(row)
      return share != null && share > 0 ? row.ingresos / (share / 100) : null
    })
    .filter((value): value is number => value != null && Number.isFinite(value) && value > 0)
    .sort((a, b) => a - b)
  if (estimates.length) return estimates[Math.floor(estimates.length / 2)]
  return rows.reduce((sum, row) => sum + row.ingresos, 0)
}

function withShares(
  rows: CategoricalChartSourceRow[],
  total: number,
): PreparedCategoricalRow[] {
  let cumulative = 0
  return rows.map((row) => {
    const share = explicitShare(row) ?? (total ? (row.ingresos / total) * 100 : 0)
    cumulative += share
    return {
      ...row,
      participacion: share,
      acumulado: Math.min(cumulative, 100),
      categorias_agrupadas: 1,
    }
  })
}

function groupOther(
  visible: PreparedCategoricalRow[],
  hidden: PreparedCategoricalRow[],
  hiddenCount: number,
  total: number,
): PreparedCategoricalRow[] {
  if (hiddenCount <= 0) return visible
  const knownHidden = hidden.reduce((sum, row) => sum + row.ingresos, 0)
  const visibleTotal = visible.reduce((sum, row) => sum + row.ingresos, 0)
  const value = Math.max(knownHidden, total - visibleTotal, 0)
  const share = total ? (value / total) * 100 : hidden.reduce((sum, row) => sum + row.participacion, 0)
  return [
    ...visible,
    {
      nombre: `Otros (${hiddenCount})`,
      ingresos: value,
      porcentaje: share,
      participacion: share,
      acumulado: 100,
      categorias_agrupadas: hiddenCount,
    },
  ]
}

/** Selector único para los cortes categóricos del Resumen. La salida ya viene
 * ordenada y agrupada para que cualquier Excel reciba la misma política. */
export function prepareCategoricalChart(
  sourceRows: CategoricalChartSourceRow[],
  options: PrepareCategoricalChartOptions = {},
): PreparedCategoricalChart {
  const cleanRows = sourceRows.filter(
    (row) => row.nombre.trim() && Number.isFinite(row.ingresos),
  )
  const totalGroups = Math.max(options.totalGroups ?? cleanRows.length, cleanRows.length)
  const total = estimateTotal(cleanRows, options.totalValue)
  const natural = isNaturalCategoryDimension(options.dimension)
  const ordered = [...cleanRows].sort((left, right) => {
    if (natural) {
      const rank = naturalCategoryRank(left.nombre) - naturalCategoryRank(right.nombre)
      return rank || left.nombre.localeCompare(right.nombre, 'es-CL')
    }
    return right.ingresos - left.ingresos || left.nombre.localeCompare(right.nombre, 'es-CL')
  })
  let rows = withShares(ordered, total)

  if (!rows.length) {
    return { kind: 'bars', rows, total, totalGroups, groupedCount: 0 }
  }

  const topShare = Math.max(...rows.map((row) => row.participacion))
  if (rows.length > 1 && topShare > 90) {
    return { kind: 'concentration', rows, total, totalGroups, groupedCount: 0 }
  }

  if (options.cumulative) {
    const visible = rows.slice(0, 10)
    const hiddenCount = Math.max(totalGroups - visible.length, 0)
    rows = groupOther(visible, rows.slice(10), hiddenCount, total)
    let cumulative = 0
    rows = rows.map((row) => ({
      ...row,
      acumulado: Math.min((cumulative += row.participacion), 100),
    }))
    return { kind: 'pareto', rows, total, totalGroups, groupedCount: hiddenCount }
  }

  if (natural) {
    return { kind: 'natural-bars', rows, total, totalGroups, groupedCount: 0 }
  }

  if (rows.length === 2 && rows.every((row) => row.ingresos >= 0)) {
    return { kind: 'stacked-100', rows, total, totalGroups, groupedCount: 0 }
  }

  if (totalGroups > 15 || rows.length > 15) {
    const visible = rows.slice(0, 10)
    const hiddenCount = Math.max(totalGroups - visible.length, 0)
    rows = groupOther(visible, rows.slice(10), hiddenCount, total)
    return { kind: 'bars', rows, total, totalGroups, groupedCount: hiddenCount }
  }

  if (rows.length >= 8) {
    const tailStart = rows.findIndex((row, index) => (
      index >= 3
      && row.participacion < 5
      && rows.slice(index).every((tail) => tail.participacion < 5)
    ))
    if (tailStart >= 0 && rows.length - tailStart >= 2) {
      const hidden = rows.slice(tailStart)
      rows = groupOther(rows.slice(0, tailStart), hidden, hidden.length, total)
      return { kind: 'bars', rows, total, totalGroups, groupedCount: hidden.length }
    }
  }

  return { kind: 'bars', rows, total, totalGroups, groupedCount: 0 }
}

export const GRID_STROKE = '#e8edf0'
export const AXIS_INK = '#5c7285' // navy atenuado para ejes/ticks

export interface RobustHeatScale {
  minimum: number
  reference: number
  maximum: number
  logarithmic: boolean
}

/** Escala robusta: el p95 conserva contraste cuando un único valor domina. */
export function buildRobustHeatScale(values: number[]): RobustHeatScale {
  const magnitudes = values
    .filter(Number.isFinite)
    .map((value) => Math.abs(value))
    .filter((value) => value > 0)
    .sort((left, right) => left - right)
  if (!magnitudes.length) return { minimum: 0, reference: 1, maximum: 0, logarithmic: false }
  const percentileIndex = Math.min(
    magnitudes.length - 1,
    Math.max(0, Math.ceil(magnitudes.length * 0.95) - 1),
  )
  const median = magnitudes[Math.floor((magnitudes.length - 1) / 2)] || 1
  const reference = magnitudes[percentileIndex] || magnitudes[magnitudes.length - 1] || 1
  const maximum = magnitudes[magnitudes.length - 1]
  return {
    minimum: magnitudes[0],
    reference,
    maximum,
    logarithmic: maximum / median >= 20,
  }
}

export function robustHeatIntensity(value: number, scale: RobustHeatScale): number {
  const magnitude = Math.abs(value)
  if (!magnitude) return 0
  const numerator = scale.logarithmic ? Math.log1p(magnitude) : magnitude
  const denominator = scale.logarithmic ? Math.log1p(scale.reference) : scale.reference
  return Math.min(numerator / Math.max(denominator, Number.EPSILON), 1)
}

/** "2026-05" → "may 26" (es-CL) para ejes y leyendas. */
export function formatMonthShort(isoMonth: string): string {
  const [year, month] = isoMonth.split('-').map(Number)
  const name = new Date(year, month - 1, 1).toLocaleDateString('es-CL', { month: 'short' })
  return `${name} ${String(year).slice(2)}`
}

/** Monto compacto para ejes: $37,0M / $850K. */
export function formatCLPCompact(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toLocaleString('es-CL', { maximumFractionDigits: 1 })}M`
  if (abs >= 1_000) return `$${Math.round(value / 1_000)}K`
  return `$${Math.round(value)}`
}

/** Recorta una etiqueta larga de eje con "…" — sin esto, el <text> SVG de
 * Recharts puede desbordar el ancho asignado y el contenedor lo recorta
 * desde el borde, comiéndose la PRIMERA letra en vez de las últimas. */
export function truncateLabel(text: string, maxLength = 18): string {
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text
}
