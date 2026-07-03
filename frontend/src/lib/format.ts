/** Formato es-CL (SPEC §10): punto de miles, coma decimal. */

const numberFormat = new Intl.NumberFormat('es-CL')

export function formatNumber(value: number): string {
  return numberFormat.format(value)
}

export function formatCLP(value: number): string {
  return `$${numberFormat.format(Math.round(value))}`
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
