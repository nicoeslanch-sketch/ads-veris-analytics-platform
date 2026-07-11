/** Formato es-CL (SPEC §10): punto de miles, coma decimal.
 *
 * Fase 11 §4.4: la moneda activa la define el backend (metrics.moneda) — una
 * base en USD ya no se muestra con formato de pesos chilenos. Las páginas que
 * reciben métricas llaman a `setActiveCurrency(metrics.moneda)` y todos los
 * montos de la sesión se formatean con esa moneda.
 */

const numberFormat = new Intl.NumberFormat('es-CL')

let activeCurrency = 'CLP'

const CURRENCY_PREFIX: Record<string, string> = {
  CLP: '$',
  USD: 'US$',
  EUR: '€',
}

export function setActiveCurrency(code: string | null | undefined): void {
  activeCurrency = code && CURRENCY_PREFIX[code] ? code : 'CLP'
}

export function getActiveCurrency(): string {
  return activeCurrency
}

export function formatNumber(value: number): string {
  return numberFormat.format(value)
}

/** Monto en la moneda ACTIVA de la sesión (histórico: nació como CLP-only). */
export function formatCLP(value: number): string {
  return `${CURRENCY_PREFIX[activeCurrency]}${numberFormat.format(Math.round(value))}`
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
