import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, Layers, Loader2, Link2, RefreshCw } from 'lucide-react'
import { useDataset } from '../../data/DatasetContext'
import { ApiError, apiPost } from '../../lib/api'
import { joinScope } from '../../lib/multiSheet'
import {
  fetchRelationshipCatalog,
  fetchRelationshipDashboard,
  pickRecommended,
  validateManualRelationship,
  type RelationshipRequestParams,
} from '../../lib/relationshipDashboard'
import type {
  AnalysisJoin,
  CatalogRelationship,
  RelationshipCandidate,
  RelationshipCatalog,
  RelationshipDashboard,
} from '../../lib/types'
import RelationshipCatalogPanel from './RelationshipCatalog'
import RelationshipDashboardView from './RelationshipDashboard'
import RelationshipBuilder, { type ManualJoinDraft } from './RelationshipBuilder'

/** Empareja el join persistido en AnalysisScope con una relación del catálogo. */
function matchingCatalogId(
  scope: ReturnType<typeof useDataset>['analysisScope'],
  relationships: CatalogRelationship[],
): string | null {
  if (scope?.mode !== 'join') return null
  const join = scope.join
  const match = relationships.find(
    (relation) =>
      relation.left_sheet === join.left_sheet &&
      relation.right_sheet === join.right_sheet &&
      relation.left_keys.join('|') === join.left_keys.join('|') &&
      relation.right_keys.join('|') === join.right_keys.join('|'),
  )
  return match?.id ?? null
}

function manualCatalogRelationship(
  join: AnalysisJoin,
  validation?: RelationshipCandidate,
): CatalogRelationship {
  return {
    ...join,
    id: `manual~${join.left_sheet}~${join.right_sheet}~${join.left_keys.join('+')}~${join.right_keys.join('+')}`,
    template: 'generic',
    label: `${join.left_sheet} ↔ ${join.right_sheet}`,
    purpose: 'manual',
    coverage_left: validation?.coverage_left ?? 0,
    coverage_right: validation?.coverage_right ?? 0,
    overlap: validation?.overlap ?? 0,
    cardinality: validation?.cardinality ?? 'muchos_a_uno',
    safe: validation?.safe ?? true,
    recommended: false,
    source: 'manual',
    currency_compatible: validation?.currency_compatible ?? true,
    reason: validation?.reason ?? null,
  }
}

function WorkspaceState({ icon: Icon, title, detail, action }: {
  icon: typeof Layers
  title: string
  detail: string
  action?: React.ReactNode
}) {
  return (
    <div className="rounded-xl border border-navy/10 bg-white p-8 text-center shadow-sm">
      <Icon className="mx-auto h-8 w-8 text-navy/30" aria-hidden />
      <p className="mt-3 text-sm font-semibold text-navy">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-xs text-navy/55">{detail}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export default function RelationshipWorkspace() {
  const {
    file,
    datasetId,
    storagePath,
    sheetManifest,
    selectedSheets,
    sheetSessions,
    analysisScope,
    period,
    restoreState,
    setAnalysisScope,
    setMonthsAvailable,
  } = useDataset()

  const cleanedSheets = useMemo(
    () => selectedSheets.filter((name) => Boolean(sheetSessions[name]?.cleaning)),
    [selectedSheets, sheetSessions],
  )
  const pendingCount = selectedSheets.filter((name) => !sheetSessions[name]?.cleaning).length
  const columnsBySheet = useMemo(
    () =>
      Object.fromEntries(
        cleanedSheets.map((name) => [name, sheetSessions[name]?.cleaning?.preview.columnas ?? []]),
      ) as Record<string, string[]>,
    [cleanedSheets, sheetSessions],
  )

  const params: RelationshipRequestParams | null = useMemo(
    () => (sheetManifest ? { file, storagePath, datasetId, manifest: sheetManifest } : null),
    [file, storagePath, datasetId, sheetManifest],
  )

  const [catalog, setCatalog] = useState<RelationshipCatalog | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [selected, setSelected] = useState<CatalogRelationship | null>(null)
  const [dashboard, setDashboard] = useState<RelationshipDashboard | null>(null)
  const [dashboardLoading, setDashboardLoading] = useState(false)
  const [dashboardError, setDashboardError] = useState<string | null>(null)
  const [builderOpen, setBuilderOpen] = useState(false)
  const [catalogRetry, setCatalogRetry] = useState(0)
  const [dashboardRetry, setDashboardRetry] = useState(0)

  const manifestKey = sheetManifest ? JSON.stringify(sheetManifest) : ''
  const scopeRef = useRef(analysisScope)
  const persistChainRef = useRef<Promise<unknown>>(Promise.resolve())
  scopeRef.current = analysisScope

  // ── Cargar el catálogo ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!params || cleanedSheets.length < 2 || pendingCount > 0) return
    const controller = new AbortController()
    setCatalogLoading(true)
    setCatalogError(null)
    fetchRelationshipCatalog(params, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        setCatalog(result)
        const activeScope = scopeRef.current
        const activeId = matchingCatalogId(activeScope, result.relationships)
        const activeAutomatic = result.relationships.find((relation) => relation.id === activeId)
        const restoredManual = activeScope?.mode === 'join' && !activeAutomatic
          ? manualCatalogRelationship(activeScope.join)
          : null
        setSelected((current) => {
          const retainedAutomatic = result.relationships.find(
            (relation) => relation.id === current?.id,
          )
          if (retainedAutomatic) return retainedAutomatic
          if (
            current?.source === 'manual' &&
            activeScope?.mode === 'join' &&
            current.left_sheet === activeScope.join.left_sheet &&
            current.right_sheet === activeScope.join.right_sheet &&
            current.left_keys.join('|') === activeScope.join.left_keys.join('|') &&
            current.right_keys.join('|') === activeScope.join.right_keys.join('|')
          ) {
            return current
          }
          return activeAutomatic ?? restoredManual ?? pickRecommended(result.relationships)
        })
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        setCatalogError(err instanceof ApiError ? err.message : 'No pudimos revisar las conexiones.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setCatalogLoading(false)
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manifestKey, cleanedSheets.length, pendingCount, catalogRetry])

  // ── Al elegir una relación, actualizar el alcance (persistente) ────────────
  const selectRelation = (relation: CatalogRelationship) => {
    setSelected(relation)
    setAnalysisScope(
      joinScope({
        left_sheet: relation.left_sheet,
        right_sheet: relation.right_sheet,
        left_keys: relation.left_keys,
        right_keys: relation.right_keys,
        type: 'left',
      }),
    )
  }

  // ── Cargar el dashboard de la relación activa ──────────────────────────────
  const selectedId = selected?.id ?? null
  useEffect(() => {
    if (!selected) return
    const scope = joinScope({
      left_sheet: selected.left_sheet,
      right_sheet: selected.right_sheet,
      left_keys: selected.left_keys,
      right_keys: selected.right_keys,
      type: 'left',
    })
    setAnalysisScope(scope)
    if (!datasetId) return

    const form = new FormData()
    form.append('dataset_id', datasetId)
    form.append(
      'restore_state',
      JSON.stringify({
        ...restoreState,
        active_sheet: selected.left_sheet,
        analysis_scope: scope,
      }),
    )
    persistChainRef.current = persistChainRef.current
      .catch(() => undefined)
      .then(() => apiPost<Record<string, unknown>>('/restore/state', form, {
        timeoutMs: 15_000,
      }))
      .catch(() => undefined)
    // La selección es la unidad de persistencia. restoreState cambia después de
    // setAnalysisScope y no debe provocar una segunda escritura de la misma relación.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, datasetId])

  useEffect(() => {
    if (!params || !selected) {
      setDashboard(null)
      return
    }
    const controller = new AbortController()
    setDashboardLoading(true)
    setDashboardError(null)
    fetchRelationshipDashboard(params, selected, { from: period.from, to: period.to }, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        setDashboard(result)
        if (result.period.meses.length) setMonthsAvailable(result.period.meses)
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        setDashboardError(err instanceof ApiError ? err.message : 'No pudimos calcular el dashboard.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setDashboardLoading(false)
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, period.from, period.to, manifestKey, dashboardRetry])

  const validateDraft = async (draft: ManualJoinDraft): Promise<RelationshipCandidate | null> => {
    if (!params) return null
    const response = await validateManualRelationship(params, draft)
    return response.manual ?? null
  }

  const useDraft = (draft: ManualJoinDraft, validation: RelationshipCandidate) => {
    const manual = manualCatalogRelationship(
      { ...draft, type: 'left' },
      validation,
    )
    setBuilderOpen(false)
    selectRelation(manual)
  }

  // ── Estados ────────────────────────────────────────────────────────────────
  if (!params || cleanedSheets.length < 2) {
    return (
      <WorkspaceState
        icon={Layers}
        title="Necesitas al menos dos hojas limpias"
        detail="El análisis de relaciones combina dos hojas del mismo libro. Prepara y limpia al menos dos hojas para conectarlas."
      />
    )
  }
  if (pendingCount > 0) {
    return (
      <WorkspaceState
        icon={Loader2}
        title="Estamos terminando la limpieza"
        detail={`Faltan ${pendingCount} hoja(s) por limpiar. El catálogo de relaciones se habilitará al terminar.`}
      />
    )
  }

  const automaticRelationships = catalog?.relationships ?? []
  const relationships = !selected || selected.source !== 'manual'
    ? automaticRelationships
    : automaticRelationships.some((relation) => relation.id === selected.id)
      ? automaticRelationships
      : [selected, ...automaticRelationships]
  const showBuilder = builderOpen && (
    <RelationshipBuilder
      sheets={cleanedSheets}
      columnsBySheet={columnsBySheet}
      onClose={() => setBuilderOpen(false)}
      onValidate={validateDraft}
      onUse={useDraft}
    />
  )

  if (catalogLoading && !catalog) {
    return (
      <div className="rounded-xl border border-navy/10 bg-white p-8 text-center shadow-sm">
        <Loader2 className="mx-auto h-6 w-6 animate-spin text-teal" aria-hidden />
        <p className="mt-3 text-sm text-navy/60">Revisando las conexiones seguras entre tus hojas…</p>
      </div>
    )
  }

  if (catalogError) {
    return (
      <WorkspaceState
        icon={AlertTriangle}
        title="No pudimos revisar las conexiones"
        detail={catalogError}
        action={
          <button
            type="button"
            onClick={() => setCatalogRetry((tick) => tick + 1)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-teal/40 px-3 py-2 text-xs font-semibold text-teal hover:bg-teal/5"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Reintentar
          </button>
        }
      />
    )
  }

  if (relationships.length === 0) {
    return (
      <>
        <WorkspaceState
          icon={Link2}
          title="No detectamos relaciones automáticas seguras"
          detail={catalog?.message ?? 'Puedes crear una conexión personalizada indicando las columnas que unen dos hojas.'}
          action={
            <button
              type="button"
              onClick={() => setBuilderOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-teal px-3 py-2 text-xs font-semibold text-white"
            >
              Crear conexión personalizada
            </button>
          }
        />
        {showBuilder}
      </>
    )
  }

  return (
    <section aria-label="Relaciones entre hojas" className="grid gap-4 min-[1100px]:grid-cols-[240px_minmax(0,1fr)]">
      <RelationshipCatalogPanel
        relationships={relationships}
        selectedId={selectedId}
        onSelect={selectRelation}
        onCreate={() => setBuilderOpen(true)}
      />
      <div className="min-w-0">
        {dashboardLoading && !dashboard ? (
          <div className="rounded-xl border border-navy/10 bg-white p-8 text-center shadow-sm">
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-teal" aria-hidden />
            <p className="mt-3 text-sm text-navy/60">Calculando el dashboard de la relación…</p>
          </div>
        ) : dashboardError ? (
          <WorkspaceState
            icon={AlertTriangle}
            title="No pudimos calcular el dashboard"
            detail={dashboardError}
            action={
              <button
                type="button"
                onClick={() => setDashboardRetry((tick) => tick + 1)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-teal/40 px-3 py-2 text-xs font-semibold text-teal hover:bg-teal/5"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Reintentar
              </button>
            }
          />
        ) : dashboard ? (
          <div className={dashboardLoading ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
            <RelationshipDashboardView dashboard={dashboard} />
          </div>
        ) : null}
      </div>
      {showBuilder}
    </section>
  )
}
