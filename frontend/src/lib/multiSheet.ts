import type {
  AnalysisJoin,
  AnalysisScope,
  DictionaryMatch,
  SheetProcessingStatus,
} from './types'

const BASIC_CRITICAL_ROLES = ['monto', 'fecha'] as const
const MEDIUM_CONFIDENCE = 0.75

export function basicMappingQuestions(
  mapping: Record<string, string>,
  extended: Record<string, DictionaryMatch>,
  confirmed: string[] = [],
): string[] {
  return BASIC_CRITICAL_ROLES.filter((role) => {
    if (confirmed.includes(role)) return false
    const column = mapping[role]
    if (!column) return true
    const match = extended[column]
    return Boolean(
      match && match.rol_motor === role && match.confianza < MEDIUM_CONFIDENCE,
    )
  })
}

export function sheetStatusLabel(
  status: SheetProcessingStatus | undefined,
  selected: boolean,
  cleaned: boolean,
): string {
  if (!selected) return 'No seleccionada'
  if (status === 'error') return 'Error'
  if (status === 'estandarizando' || status === 'limpiando') return 'Procesando...'
  if (cleaned || status === 'limpia') return 'Estandarizada y limpia'
  if (status === 'estandarizada') return 'Estandarizada'
  return 'Pendiente'
}

export type SheetPreparationAction = 'prepare' | 'update' | null

interface SheetPreparationState {
  standardization?: unknown
  status?: string
}

/** Decides whether the selection still needs work without coupling the UI to
 * the persistence layer. A fully prepared selection has no action at all. */
export function sheetPreparationAction(
  selectedSheets: string[],
  sessions: Record<string, SheetPreparationState | undefined>,
): SheetPreparationAction {
  if (selectedSheets.length === 0) return null
  const prepared = selectedSheets.filter((name) => Boolean(sessions[name]?.standardization)).length
  if (prepared === selectedSheets.length) return null
  return prepared > 0 ? 'update' : 'prepare'
}

/** In "all" mode every pending sheet is prepared automatically. Failed sheets
 * stay manual so a persistent error cannot start an automatic retry loop. */
export function sheetsForAutomaticPreparation(
  mode: 'all' | 'custom',
  availableSheets: string[],
  sessions: Record<string, SheetPreparationState | undefined>,
  selectedSheets: string[] = availableSheets,
): string[] {
  if (mode !== 'all') return []
  return availableSheets.filter((name) => selectedSheets.includes(name)).filter((name) => {
    const session = sessions[name]
    return !session?.standardization &&
      session?.status !== 'error' &&
      session?.status !== 'estandarizando'
  })
}

export function sheetSelectionCountLabel(
  mode: 'all' | 'custom',
  selected: number,
  total: number,
): string | null {
  return mode === 'all' ? null : `${selected} de ${total} hojas seleccionadas`
}

export function standardizationScopeComplete(
  selectedSheets: string[],
  sessions: Record<string, { standardization?: unknown } | undefined>,
): boolean {
  return selectedSheets.length > 0 && selectedSheets.every(
    (name) => Boolean(sessions[name]?.standardization),
  )
}

export function cleaningScopeState(
  selectedSheets: string[],
  sessions: Record<string, { standardization?: unknown; cleaning?: unknown; status?: string } | undefined>,
  running = false,
): 'pending' | 'cleaning' | 'partial' | 'complete' | 'complete_with_errors' {
  if (running) return 'cleaning'
  const errors = selectedSheets.filter((name) => sessions[name]?.status === 'error').length
  const cleaned = selectedSheets.filter((name) => Boolean(sessions[name]?.cleaning)).length
  if (errors > 0) return 'complete_with_errors'
  if (selectedSheets.length > 0 && cleaned === selectedSheets.length) return 'complete'
  if (cleaned > 0) return 'partial'
  return 'pending'
}

interface AppendCompatibilityResult {
  preview: { columnas: string[] }
  column_types: Record<string, string>
  mapeo: Record<string, string>
  moneda?: string
  moneda_mixta?: boolean
  moneda_detalle?: { dominante: string }
}

export function compatibleAppendSheets(
  sheets: string[],
  results: Record<string, AppendCompatibilityResult | null | undefined>,
): string[] {
  const signature = (name: string) => {
    const result = results[name]
    if (!result || result.moneda_mixta) return null
    return JSON.stringify({
      columns: [...result.preview.columnas].sort(),
      types: Object.entries(result.column_types).sort(([left], [right]) => left.localeCompare(right)),
      mapping: Object.entries(result.mapeo).sort(([left], [right]) => left.localeCompare(right)),
      currency: result.moneda_detalle?.dominante ?? result.moneda ?? 'CLP',
    })
  }
  const base = sheets[0]
  const baseSignature = base ? signature(base) : null
  return sheets.filter((name) => baseSignature !== null && signature(name) === baseSignature)
}

export function singleScope(sheet: string): AnalysisScope {
  return { mode: 'single', sheets: [sheet], active_sheet: sheet }
}

export function appendScope(sheets: string[]): AnalysisScope | null {
  const unique = [...new Set(sheets)]
  return unique.length >= 2
    ? { mode: 'append', sheets: unique, active_sheet: unique[0] }
    : null
}

export function joinScope(join: AnalysisJoin): AnalysisScope {
  return {
    mode: 'join',
    sheets: [join.left_sheet, join.right_sheet],
    active_sheet: join.left_sheet,
    join,
  }
}
