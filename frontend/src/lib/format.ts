/** Formato es-CL (SPEC §10): punto de miles, coma decimal.
 *
 * Fase 11 §4.4: la moneda activa la define el backend (metrics.moneda) — una
 * base en USD ya no se muestra con formato de pesos chilenos. Las páginas que
 * reciben métricas llaman a `setActiveCurrency(metrics.moneda)` y todos los
 * montos de la sesión se formatean con esa moneda.
 */

const numberFormat = new Intl.NumberFormat('es-CL')
const amountFormats = [0, 2].map((digits) => new Intl.NumberFormat('es-CL', {
  minimumFractionDigits: digits,
  maximumFractionDigits: digits === 2 ? 8 : 0,
}))
const compactFormats = [0, 1, 2].map((digits) => new Intl.NumberFormat('es-CL', {
  maximumFractionDigits: digits,
}))
const ufCompactFormat = new Intl.NumberFormat('es-CL', { maximumFractionDigits: 8 })
const fractionalAmountFormat = new Intl.NumberFormat('es-CL', {
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

function tinyUf(value: number): string | null {
  if (value === 0 || Math.abs(value) >= 1e-8) return null
  return value > 0 ? '<UF 0,00000001' : '>UF -0,00000001'
}

let activeCurrency = 'CLP'

const CURRENCY_PREFIX: Record<string, string> = {
  CLP: '$',
  UF: 'UF ',
  USD: 'US$',
  EUR: '€',
  ARS: 'ARS ',
  PEN: 'PEN ',
  COP: 'COP ',
  MXN: 'MXN ',
  GBP: '£',
}

export function setActiveCurrency(code: string | null | undefined): void {
  activeCurrency = code && CURRENCY_PREFIX[code] ? code : 'CLP'
}

export function getActiveCurrency(): string {
  return activeCurrency
}

export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return '\u2014'
  return numberFormat.format(value)
}

/** Monto en la moneda ACTIVA de la sesión (histórico: nació como CLP-only). */
export function formatCLP(value: number): string {
  if (!Number.isFinite(value)) return '\u2014'
  if (activeCurrency === 'UF' && tinyUf(value)) return tinyUf(value)!
  const formatter = activeCurrency === 'UF' && !Number.isInteger(value) ? amountFormats[1]
    : activeCurrency !== 'CLP' && !Number.isInteger(value) ? fractionalAmountFormat : amountFormats[0]
  const formatted = formatter.format(value)
  return `${CURRENCY_PREFIX[activeCurrency]}${formatted}`
}

export function formatCurrencyCompact(value: number, currency = activeCurrency): string {
  if (!Number.isFinite(value)) return '\u2014'
  const code = CURRENCY_PREFIX[currency] ? currency : 'CLP'
  if (code === 'UF' && tinyUf(value)) return tinyUf(value)!
  const magnitude = Math.abs(value)
  const divisor = magnitude >= 1_000_000 ? 1_000_000 : magnitude >= 1_000 ? 1_000 : 1
  const suffix = divisor === 1_000_000 ? 'M' : divisor === 1_000 ? 'K' : ''
  const digits = divisor > 1 ? 1 : code !== 'CLP' ? 2 : 0
  const formatter = code === 'UF' && divisor === 1 ? ufCompactFormat : compactFormats[digits]
  return `${CURRENCY_PREFIX[code]}${formatter.format(value / divisor)}${suffix}`
}

export function formatDateTime(date: Date): string {
  return date.toLocaleString('es-CL', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** "hace 2 horas" / "hace 3 días" — legible para Actividad reciente. Más
 * allá de un mes cae a la fecha absoluta (una relativa deja de ser útil). */
export function formatRelativeTime(date: Date): string {
  const diffMin = Math.round((Date.now() - date.getTime()) / 60_000)
  if (diffMin < 1) return 'hace un momento'
  if (diffMin < 60) return `hace ${diffMin} minuto${diffMin === 1 ? '' : 's'}`
  const diffHour = Math.round(diffMin / 60)
  if (diffHour < 24) return `hace ${diffHour} hora${diffHour === 1 ? '' : 's'}`
  const diffDay = Math.round(diffHour / 24)
  if (diffDay < 30) return `hace ${diffDay} día${diffDay === 1 ? '' : 's'}`
  return formatDateTime(date)
}

// El path de Storage antepone Date.now()_ al nombre (lib/datasets.ts) para
// evitar colisiones; el backend ya devuelve `archivo` limpio
// (_display_filename en pipeline.py), pero se sanea también aquí como
// respaldo — por si una sesión quedó con un valor cacheado de antes del fix
// desplegado, o aparece otro punto que aún no pasa por esa limpieza.
const STORAGE_TIMESTAMP_PREFIX_RE = /\b\d{10,}_/g

export function cleanFilename(name: string): string {
  return name.replace(STORAGE_TIMESTAMP_PREFIX_RE, '')
}
