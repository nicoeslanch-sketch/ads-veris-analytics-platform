import type { GroupRow, MetricsResult } from './types'

export type SummaryContentKind =
  | 'mixed_currency'
  | 'product_catalog'
  | 'adaptive_profile'
  | 'missing_amount'
  | 'financial'

/** El bloqueo global de monedas siempre tiene prioridad, incluso cuando la
 * misma respuesta también incluye un perfil de Productos o Campañas. */
export function summaryContentKind(metrics: MetricsResult): SummaryContentKind {
  if (metrics.moneda_mixta) return 'mixed_currency'
  if (metrics.analisis_productos) return 'product_catalog'
  if (metrics.analisis_campanas || metrics.analisis_inventario || metrics.analisis_generico) {
    return 'adaptive_profile'
  }
  if (metrics.dimensiones?.monto === false) return 'missing_amount'
  return 'financial'
}

/** Elemento con mayor participación bruta.
 *
 * Las listas del motor se ordenan por ingresos netos para que tablas y barras
 * sigan siendo coherentes. Las afirmaciones de concentración deben seleccionar
 * explícitamente por ventas brutas, no asumir que el primer elemento sirve para
 * ambos criterios.
 */
export function principalPorParticipacionBruta(
  rows: readonly GroupRow[],
): GroupRow | undefined {
  return rows.reduce<GroupRow | undefined>((principal, row) => {
    if (!principal) return row
    const actual = row.participacion_bruta_pct ?? row.porcentaje
    const mayor = principal.participacion_bruta_pct ?? principal.porcentaje
    return actual > mayor ? row : principal
  }, undefined)
}
