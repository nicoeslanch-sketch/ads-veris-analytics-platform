export function formatNumber(value: number): string {
  return new Intl.NumberFormat('es-CL').format(value)
}

export function formatDateTime(value: Date): string {
  return new Intl.DateTimeFormat('es-CL', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(value)
}
