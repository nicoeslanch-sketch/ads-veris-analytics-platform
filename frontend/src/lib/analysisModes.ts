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
  { mode: 'append', label: 'Consolidar períodos de venta' },
  { mode: 'join', label: 'Relación manual' },
]

/** El modo interno del texto de un botón (o undefined si no existe). */
export function internalModeForLabel(label: string): AnalysisMode | undefined {
  if (label === 'Unir periodos de venta' || label === 'Unir períodos de venta') return 'append'
  return ANALYSIS_MODES.find((entry) => entry.label === label)?.mode
}

/** Mensaje de espera específico del alcance. Nunca atribuye a una sola hoja
 * un cálculo que en realidad apila varios períodos. */
export function analysisLoadingOperation(mode: AnalysisMode, sheet?: string | null): string {
  if (mode === 'append') return 'Procesando todos los períodos de venta'
  if (mode === 'append_join') return 'Calculando la visión completa del negocio'
  if (mode === 'join') return 'Procesando la relación seleccionada'
  return `Calculando indicadores${sheet ? ` de ${sheet}` : ''}`
}
