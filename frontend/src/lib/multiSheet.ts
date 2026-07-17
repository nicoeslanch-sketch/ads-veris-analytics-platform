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
