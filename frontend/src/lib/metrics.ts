import type { GroupRow } from './types'

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
