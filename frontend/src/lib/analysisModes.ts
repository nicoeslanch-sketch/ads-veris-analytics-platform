import type { AnalysisScope } from './types'

export type AnalysisMode = AnalysisScope['mode']

/** Definición ÚNICA y pura de los cuatro modos de análisis: su texto EXACTO,
 * su orden y el modo interno que ejecutan. La botonera solo la renderiza.
 *
 * Invariante crítico (Parte 1): los tres primeros modos deben seguir mapeando
 * a `single`, `append_join` y `append`. "Relación manual" usa `join`. */
export const ANALYSIS_MODES: ReadonlyArray<{ mode: AnalysisMode; label: string }> = [
  { mode: 'single', label: 'Analizar una hoja' },
  { mode: 'append_join', label: 'Visión del negocio' },
  { mode: 'append', label: 'Unir periodos de venta' },
  { mode: 'join', label: 'Relación manual' },
]

/** El modo interno del texto de un botón (o undefined si no existe). */
export function internalModeForLabel(label: string): AnalysisMode | undefined {
  return ANALYSIS_MODES.find((entry) => entry.label === label)?.mode
}
