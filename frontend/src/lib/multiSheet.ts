import type {
  AnalysisJoin,
  AnalysisScope,
  CleaningRules,
  DictionaryMatch,
  RelationshipCandidate,
  SheetProcessingStatus,
} from './types'

const BASIC_CRITICAL_ROLES = ['monto', 'fecha'] as const
const MEDIUM_CONFIDENCE = 0.75

type SheetSelectionMode = 'all' | 'custom'

export interface SheetSelectionRestoreState {
  active_sheet: string | null
  available_sheets: string[]
  excluded_sheets: string[]
  selected_sheets: string[]
  analysis_scope: AnalysisScope | null
  selection_mode: SheetSelectionMode
}

/** Applies a sheet selection to the persisted restore contract. Any analysis
 * scope that references an excluded sheet is reduced to the first selected
 * sheet so a reload cannot revive the previous, broader scope. */
export function withSheetSelection(
  state: SheetSelectionRestoreState,
  names: string[],
  mode: SheetSelectionMode,
): SheetSelectionRestoreState {
  const selected = names.filter(
    (name, index) => state.available_sheets.includes(name) && names.indexOf(name) === index,
  )
  const active = state.active_sheet && selected.includes(state.active_sheet)
    ? state.active_sheet
    : (selected[0] ?? null)
  const currentScope = publicAnalysisScope(state.analysis_scope)
  const scope = currentScope && currentScope.sheets.every((name) => selected.includes(name))
    ? currentScope
    : active
      ? { mode: 'single' as const, sheets: [active], active_sheet: active }
      : null
  return {
    ...state,
    active_sheet: active,
    selected_sheets: selected,
    excluded_sheets: state.available_sheets.filter((name) => !selected.includes(name)),
    analysis_scope: scope,
    selection_mode: mode,
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function stringList(value: unknown): string[] | null {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
    ? [...value]
    : null
}

function publicJoin(value: unknown): AnalysisJoin | null {
  if (!isRecord(value)) return null
  const leftKeys = stringList(value.left_keys)
  const rightKeys = stringList(value.right_keys)
  if (
    typeof value.left_sheet !== 'string' ||
    typeof value.right_sheet !== 'string' ||
    value.type !== 'left' ||
    !leftKeys ||
    !rightKeys
  ) return null
  return {
    left_sheet: value.left_sheet,
    right_sheet: value.right_sheet,
    left_keys: leftKeys,
    right_keys: rightKeys,
    type: 'left',
  }
}

/** Keeps persistence-only metadata out of API payloads. During a rolling
 * deployment the database can contain fields that an older API does not yet
 * understand, so the browser only exposes the public AnalysisScope contract. */
export function publicAnalysisScope(value: unknown): AnalysisScope | null {
  if (!isRecord(value)) return null
  const sheets = stringList(value.sheets)
  if (!sheets || typeof value.active_sheet !== 'string') return null
  if (value.mode === 'single' || value.mode === 'append') {
    return { mode: value.mode, sheets, active_sheet: value.active_sheet }
  }
  if (value.mode === 'join') {
    const join = publicJoin(value.join)
    return join ? { mode: 'join', sheets, active_sheet: value.active_sheet, join } : null
  }
  if (value.mode === 'append_join') {
    const join = publicJoin(value.join)
    const appendSheets = stringList(value.append_sheets)
    return join && appendSheets
      ? {
          mode: 'append_join',
          sheets,
          append_sheets: appendSheets,
          active_sheet: value.active_sheet,
          join,
        }
      : null
  }
  return null
}

export function restoredAnalysisSelection(
  value: unknown,
  explicitMode?: SheetSelectionMode,
): { analysisScope: AnalysisScope | null; selectionMode: SheetSelectionMode } {
  const storedMode = isRecord(value) &&
    (value._selection_mode === 'all' || value._selection_mode === 'custom')
    ? value._selection_mode
    : null
  return {
    analysisScope: publicAnalysisScope(value),
    selectionMode: explicitMode ?? storedMode ?? 'all',
  }
}

export function serializedAnalysisScope(value: unknown): string | null {
  const scope = publicAnalysisScope(value)
  return scope ? JSON.stringify(scope) : null
}

/** Compares the public, serializable contract instead of object identity. */
export function analysisScopesEqual(left: unknown, right: unknown): boolean {
  return serializedAnalysisScope(left) === serializedAnalysisScope(right)
}

export function withPublicAnalysisScope<T extends object>(value: T): T {
  const result = { ...value } as T & { analysis_scope?: unknown }
  if (!Object.prototype.hasOwnProperty.call(result, 'analysis_scope')) return result
  const scope = publicAnalysisScope(result.analysis_scope)
  if (scope) result.analysis_scope = scope
  else delete result.analysis_scope
  return result
}

export function basicMappingQuestions(
  mapping: Record<string, string>,
  extended: Record<string, DictionaryMatch>,
  confirmed: string[] = [],
  columnTypes?: Record<string, string>,
): string[] {
  // Fase 18: si la hoja NO tiene ninguna columna del tipo pedido (una maestra
  // de clientes no trae fechas de venta ni montos), preguntar "¿en qué columna
  // está la fecha?" solo confunde. Sin candidatas, la pregunta se omite y la
  // UI explica que la hoja no es transaccional.
  const hasCandidate = (role: string): boolean => {
    if (!columnTypes) return true
    const wanted = role === 'fecha' ? 'fecha' : 'numero'
    return Object.values(columnTypes).some((tipo) => tipo === wanted)
  }
  return BASIC_CRITICAL_ROLES.filter((role) => {
    if (confirmed.includes(role)) return false
    const column = mapping[role]
    if (!column) return hasCandidate(role)
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
  if (errors > 0 && cleaned + errors === selectedSheets.length) return 'complete_with_errors'
  if (selectedSheets.length > 0 && cleaned === selectedSheets.length) return 'complete'
  if (cleaned > 0 || errors > 0) return 'partial'
  return 'pending'
}

/** Hojas preparadas que pueden limpiarse en lote sin reintentar errores ni
 * repetir trabajo ya completado. La eliminacion de duplicados sigue siendo
 * una confirmacion separada; esta seleccion solo aplica las reglas estandar. */
export function sheetsForAutomaticCleaning(
  selectedSheets: string[],
  sessions: Record<string, { standardization?: unknown; cleaning?: unknown; status?: string } | undefined>,
): string[] {
  if (selectedSheets.length <= 1) return []
  return selectedSheets.filter((name) => {
    const session = sessions[name]
    return Boolean(session?.standardization) &&
      !session?.cleaning &&
      session?.status !== 'error' &&
      session?.status !== 'limpiando'
  })
}

interface AutomaticCleaningSession {
  standardization?: { revision?: number | null } | null
  cleaning?: { revision?: number | null; reglas_activas?: CleaningRules } | null
  mappingOverride?: Record<string, string> | null
  status?: string
}

function stableObjectEntries(value: object | null | undefined) {
  return value
    ? Object.entries(value).sort(([left], [right]) => left.localeCompare(right))
    : []
}

/** Firma exacta de la preparación que dispara la limpieza automática.
 * La revisión de estandarización por sí sola no basta: un cambio manual de
 * mapeo invalida `cleaning` sin crear otra revisión de estandarización. */
export function automaticCleaningSignature(
  datasetKey: string,
  selectedSheets: string[],
  sessions: Record<string, AutomaticCleaningSession | undefined>,
  rules: CleaningRules,
): string {
  return JSON.stringify({
    dataset: datasetKey,
    rules: stableObjectEntries(rules),
    sheets: selectedSheets.map((name) => {
      const session = sessions[name]
      return {
        name,
        standardization_revision: session?.standardization?.revision ?? 0,
        mapping: stableObjectEntries(session?.mappingOverride),
        cleaning_revision: session?.cleaning?.revision ?? null,
        cleaning_rules: stableObjectEntries(session?.cleaning?.reglas_activas),
        status: session?.status ?? 'pendiente',
      }
    }),
  })
}

/** Mantiene el estado restaurable de errores durante una limpieza por lote.
 * Un reintento exitoso elimina el error anterior; un fallo posterior queda
 * acumulado para que la siguiente peticion y el guardado final lo conozcan. */
export function updateBatchSheetErrors(
  current: Record<string, string>,
  sheet: string,
  error: string | null,
): Record<string, string> {
  const next = { ...current }
  if (error) next[sheet] = error
  else delete next[sheet]
  return next
}

/** Al restaurar, un error persistido tiene prioridad sobre un resultado
 * anterior: la hoja debe volver a ofrecer reintento y no figurar como limpia. */
export function restoredSheetStatus(
  error: string | null | undefined,
  hasCleaning: boolean,
): SheetProcessingStatus {
  if (error) return 'error'
  return hasCleaning ? 'limpia' : 'estandarizada'
}

interface AppendCompatibilityResult {
  preview: { columnas: string[] }
  column_types: Record<string, string>
  mapeo: Record<string, string>
  moneda?: string
  moneda_mixta?: boolean
  moneda_detalle?: { dominante: string }
}

function normalizedColumnName(value: string | undefined): string {
  return (value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
}

function looksLikeProductCatalog(result: AppendCompatibilityResult | null | undefined): boolean {
  if (!result) return false
  const mapping = result.mapeo
  const hasListPrice = result.preview.columnas.some((column) => {
    const normalized = normalizedColumnName(column)
    return normalized.includes('precio_lista') ||
      normalized.includes('lista_precio') ||
      normalized.includes('list_price') ||
      normalized.includes('price_list') ||
      normalized === 'pvp'
  })
  return Boolean(mapping.producto && mapping.costo && !mapping.fecha && hasListPrice)
}

function transactionGroupScore(
  group: string[],
  results: Record<string, AppendCompatibilityResult | null | undefined>,
): number {
  return group.filter((name) => {
    const result = results[name]
    const mapping = result?.mapeo ?? {}
    return Boolean(
      mapping.monto &&
      (mapping.cantidad || mapping.fecha) &&
      !looksLikeProductCatalog(result),
    )
  }).length
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
  const groups = new Map<string, string[]>()
  for (const name of sheets) {
    const current = signature(name)
    if (current === null) continue
    groups.set(current, [...(groups.get(current) ?? []), name])
  }
  // Keep a one-sheet transaction group: it can still be related to a product
  // catalog even though there is nothing to append.
  const candidates = [...groups.values()]
  candidates.sort((left, right) => {
    const scoreDifference = transactionGroupScore(right, results) - transactionGroupScore(left, results)
    if (scoreDifference !== 0) return scoreDifference
    return right.length - left.length
  })
  return candidates[0] ?? []
}

type AppendJoinScope = Extract<AnalysisScope, { mode: 'append_join' }>

export interface AppendJoinSelectionUpdate {
  appendSheets: string[]
  scope: AppendJoinScope
  blocked: 'minimum_one_sheet' | null
}

/** Keeps the checkbox selection and scope aligned while a new relationship is
 * validated. The left sheet only represents the stacked sales dataset. */
export function synchronizeAppendJoinSelection(
  scope: AppendJoinScope,
  requestedSheets: string[],
  compatibleSheets: string[],
): AppendJoinSelectionUpdate {
  const normalized = compatibleSheets.filter(
    (name, index) => requestedSheets.includes(name) && compatibleSheets.indexOf(name) === index,
  )
  if (normalized.length < 1) {
    return {
      appendSheets: scope.append_sheets,
      scope,
      blocked: 'minimum_one_sheet',
    }
  }
  const representative = normalized.includes(scope.join.left_sheet)
    ? scope.join.left_sheet
    : normalized[0]
  const sheets = [...new Set([...normalized, scope.join.right_sheet])]
  const unchanged = normalized.length === scope.append_sheets.length &&
    normalized.every((name, index) => name === scope.append_sheets[index]) &&
    representative === scope.join.left_sheet &&
    sheets.length === scope.sheets.length &&
    sheets.every((name, index) => name === scope.sheets[index])
  if (unchanged) return { appendSheets: scope.append_sheets, scope, blocked: null }
  return {
    appendSheets: normalized,
    scope: {
      ...scope,
      append_sheets: normalized,
      sheets,
      active_sheet: representative,
      join: { ...scope.join, left_sheet: representative },
    },
    blocked: null,
  }
}

export function relationshipPlainMessage(candidate: RelationshipCandidate): string {
  if (candidate.safe) {
    return `La unión es segura: ${Math.round(candidate.coverage_left * 100)} de cada 100 filas tienen clave y ${Math.round(candidate.overlap * 100)} de cada 100 claves encuentran correspondencia. No aumentará las filas.`
  }
  if (candidate.currency_compatible === false) {
    return candidate.reason ?? 'Las monedas no son compatibles para calcular costos y utilidad.'
  }
  if (candidate.overlap === 0) {
    return 'Ningún identificador de la primera hoja existe en la segunda; la unión no agregaría información.'
  }
  if (candidate.cardinality === 'muchos_a_muchos' || candidate.cardinality === 'uno_a_muchos') {
    return 'La hoja de referencia repite identificadores y podría multiplicar ventas. Corrige esa clave o elige otra hoja.'
  }
  return candidate.reason ?? 'La relación no es segura con las columnas elegidas.'
}

export interface AppendJoinCostCandidates {
  candidates: RelationshipCandidate[]
  automatic: RelationshipCandidate | null
  blocked: RelationshipCandidate | null
}

/** El flujo rápido "Ventas + costos" no debe convertir una relación genérica
 * con Clientes o Sucursales en costos. Solo expone candidatos cuyo propósito
 * declarado por el backend es enriquecer costos, y solo autoelige uno marcado
 * explícitamente como recomendado. */
export function selectAppendJoinCostCandidates(
  candidates: RelationshipCandidate[],
  appendSheets: string[],
): AppendJoinCostCandidates {
  const costCandidates = candidates.filter((candidate) => (
    candidate.purpose === 'enriquecer_costos' &&
    appendSheets.includes(candidate.left_sheet) &&
    !appendSheets.includes(candidate.right_sheet)
  ))
  const safe = costCandidates
    .filter((candidate) => candidate.safe)
    .sort((left, right) => Number(Boolean(right.recommended)) - Number(Boolean(left.recommended)))
  const blocked = costCandidates
    .filter((candidate) => !candidate.safe)
    .sort((left, right) => {
      const currencyDifference = Number(left.currency_compatible !== false) -
        Number(right.currency_compatible !== false)
      if (currencyDifference !== 0) return currencyDifference
      return Number(Boolean(right.recommended)) - Number(Boolean(left.recommended))
    })[0] ?? null
  return {
    candidates: safe,
    automatic: safe.find((candidate) => candidate.recommended) ?? null,
    blocked,
  }
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
