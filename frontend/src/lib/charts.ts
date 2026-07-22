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
  return rows.length >= 2 && rows.length <= 5 && rows.every((row) => row.registros >= 0)
    ? 'donut'
    : 'bars'
}

export const GRID_STROKE = '#e8edf0'
export const AXIS_INK = '#5c7285' // navy atenuado para ejes/ticks

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
