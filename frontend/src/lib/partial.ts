/** Meses parciales — helper ÚNICO para todos los consumidores (Fase 14b).
 *
 * Regla transversal: un mes con cobertura parcial (el backend lo marca con
 * los DATOS, no con el reloj) jamás compite ni se compara contra meses
 * completos — ni en Alertas, ni en Resumen, ni en Explorar. Puede mostrarse
 * visualmente, pero no define variaciones, mejor/peor mes ni hallazgos.
 */

import type { MetricsResult } from './types'

export type EvolucionMes = MetricsResult['evolucion_mensual'][number]

/** Serie sin meses parciales — para variaciones, mejor/peor mes y hallazgos. */
export function soloMesesCompletos<T extends { parcial?: boolean }>(evolucion: T[]): T[] {
  return evolucion.filter((mes) => !mes.parcial)
}

/** El mes parcial de la serie (el backend solo marca el último), o null. */
export function mesParcialDe<T extends { parcial?: boolean }>(evolucion: T[]): T | null {
  return evolucion.find((mes) => mes.parcial) ?? null
}
