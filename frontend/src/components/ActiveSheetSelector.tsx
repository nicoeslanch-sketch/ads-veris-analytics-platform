import { AlertTriangle, CheckCircle2, Link2, Loader2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useDataset } from '../data/DatasetContext'
import { ApiError, apiPost, buildDatasetForm } from '../lib/api'
import { cacheRelationships, getCachedRelationships } from '../lib/analysisCache'
import {
  compatibleAppendSheets,
  relationshipPlainMessage,
  selectAppendJoinCostCandidates,
  shouldAutoBuildBusinessScope,
} from '../lib/multiSheet'
import type { AnalysisScope, RelationshipCandidate, RelationshipResult } from '../lib/types'
import { usePlan } from '../lib/usePlan'
import AnalysisModeSwitcher from './summary/AnalysisModeSwitcher'

type Mode = AnalysisScope['mode']

interface ActiveSheetSelectorProps {
  /** Notifica a la página el modo actual para decidir si mostrar el workspace
   * de relaciones (mode === 'join') en lugar del dashboard genérico. */
  onModeChange?: (mode: Mode) => void
  /** Al incrementar, abre "Relación manual" desde fuera (lo usa el aviso de
   * relación bloqueada, cuya única salida real es cambiar la relación). */
  openRelationsNonce?: number
}

export default function ActiveSheetSelector({
  onModeChange,
  openRelationsNonce,
}: ActiveSheetSelectorProps = {}) {
  const location = useLocation()
  const {
    file,
    datasetId,
    storagePath,
    sheet,
    availableSheets,
    selectedSheets,
    sheetSessions,
    sheetManifest,
    analysisScope,
    metrics,
    cleaning,
    setAnalysisScope,
    setMetrics,
    setSheet,
  } = useDataset()
  const { plan } = usePlan()
  const advanced = plan === 'analista' || plan === 'gold'
  const cleanedSheets = useMemo(
    () => {
      if (availableSheets.length === 0 && cleaning) return ['Archivo único']
      return availableSheets.filter(
        (name) => selectedSheets.includes(name) && Boolean(
          sheetSessions[name]?.cleaning
          || (availableSheets.length === 1 && cleaning && name === sheet),
        ),
      )
    },
    [availableSheets, cleaning, selectedSheets, sheet, sheetSessions],
  )
  const compatibleSheets = useMemo(() => {
    return compatibleAppendSheets(
      cleanedSheets,
      Object.fromEntries(cleanedSheets.map((name) => [name, sheetSessions[name]?.cleaning])),
    )
  }, [cleanedSheets, sheetSessions])
  const pendingSelectedCount = availableSheets.length === 0 && cleaning
    ? 0
    : selectedSheets.filter((name) => !(
        sheetSessions[name]?.cleaning
        || (availableSheets.length === 1 && cleaning && name === sheet)
      )).length
  const requestedMode = (
    new URLSearchParams(location.search).get('mode')
    ?? (location.state as { analysisMode?: unknown } | null)?.analysisMode
  )
  const initialMode: Mode = requestedMode === 'join'
    ? 'join'
    : analysisScope?.mode ?? 'single'
  const [mode, setMode] = useState<Mode>(initialMode)
  const [appendSheets, setAppendSheets] = useState<string[]>(
    analysisScope?.mode === 'append'
      ? analysisScope.sheets
      : analysisScope?.mode === 'append_join'
        ? analysisScope.append_sheets
        : compatibleSheets,
  )
  const [candidates, setCandidates] = useState<RelationshipCandidate[]>([])
  const [relationMessage, setRelationMessage] = useState<string | null>(null)
  const [detecting, setDetecting] = useState(false)
  const autoBusinessAttempt = useRef<string | null>(null)
  const manualModeSelected = useRef(false)

  useEffect(() => {
    if (requestedMode === 'join') {
      manualModeSelected.current = true
      setMode('join')
      return
    }
    if (analysisScope) {
      setMode(analysisScope.mode)
      return
    }
    if (sheet) setMode('single')
  }, [analysisScope, requestedMode, sheet])

  // Mantiene informada a la página del modo activo (para el workspace de join).
  useEffect(() => {
    onModeChange?.(mode)
  }, [mode, onModeChange])

  // Apertura de "Relación manual" pedida por la página. Se ignora el valor
  // inicial: solo un incremento posterior representa una acción del usuario.
  const initialRelationsNonce = useRef(openRelationsNonce)
  useEffect(() => {
    if (openRelationsNonce === undefined) return
    if (openRelationsNonce === initialRelationsNonce.current) return
    manualModeSelected.current = true
    setMode('join')
  }, [openRelationsNonce])

  useEffect(() => {
    if (compatibleSheets.length < 1) return
    setAppendSheets((current) => {
      const stillCompatible = current.filter((name) => compatibleSheets.includes(name))
      const next = stillCompatible.length >= 1 ? stillCompatible : compatibleSheets
      return next.length === current.length && next.every((name, index) => name === current[index])
        ? current
        : next
    })
  }, [compatibleSheets])

  const activeAppendJoin = mode === 'append_join' && analysisScope?.mode === 'append_join'
    ? analysisScope
    : null
  const activeRelationCandidate = activeAppendJoin
    ? candidates.find((candidate) => (
        candidate.left_sheet === activeAppendJoin.join.left_sheet &&
        candidate.right_sheet === activeAppendJoin.join.right_sheet &&
        candidate.left_keys.join('|') === activeAppendJoin.join.left_keys.join('|')
      )) ?? null
    : null
  const analysisProvenance = metrics?.analysis_provenance as
    | { rows?: unknown; join?: { filas_sin_correspondencia?: unknown } }
    | undefined
  const activeRows = typeof analysisProvenance?.rows === 'number'
    ? analysisProvenance.rows
    : null
  const unmatchedRows = typeof analysisProvenance?.join?.filas_sin_correspondencia === 'number'
    ? analysisProvenance.join.filas_sin_correspondencia
    : null

  useEffect(() => {
    if (
      !file ||
      !sheetManifest ||
      manualModeSelected.current ||
      detecting ||
      !shouldAutoBuildBusinessScope(
        analysisScope,
        selectedSheets,
        cleanedSheets,
        compatibleSheets,
        pendingSelectedCount,
      )
    ) return
    const datasetKey = datasetId ?? storagePath ?? `${file.name}:${file.size}:${file.lastModified}`
    const attemptKey = `${datasetKey}|${compatibleSheets.join('|')}`
    if (autoBusinessAttempt.current === attemptKey) return
    autoBusinessAttempt.current = attemptKey
    void findRelationships('append_join', compatibleSheets)
    // `findRelationships` intentionally reads the current manifest. The
    // stable dataset/sheet signature above prevents request loops.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisScope, cleanedSheets, compatibleSheets, datasetId, detecting, file, pendingSelectedCount, selectedSheets, sheetManifest, storagePath])

  // Antes se ocultaba con una sola hoja limpia. Durante una limpieza
  // multihoja eso obligaba a refrescar para que el contexto restaurado
  // mostrara finalmente "Datos que estás analizando".
  if (!file || cleanedSheets.length === 0) return null

  const activeCleanedSheet = sheet && cleanedSheets.includes(sheet)
    ? sheet
    : cleanedSheets[0]

  const chooseSingle = (name: string) => {
    setSheet(name)
    setAnalysisScope({ mode: 'single', sheets: [name], active_sheet: name })
  }

  const chooseAppend = (names: string[]) => {
    const unique = compatibleSheets.filter((name) => names.includes(name))
    setAppendSheets((current) => (
      unique.length === current.length && unique.every((name, index) => name === current[index])
        ? current
        : unique
    ))
    if (unique.length >= 2) {
      setSheet(unique[0])
      setAnalysisScope({ mode: 'append', sheets: unique, active_sheet: unique[0] })
    }
  }

  const chooseAppendJoin = (names: string[]) => {
    if (detecting) return
    const unique = compatibleSheets.filter((name) => names.includes(name))
    if (unique.length < 1) {
      setRelationMessage('Selecciona al menos una hoja de ventas para agregar sus costos.')
      return
    }
    setAppendSheets((current) => (
      unique.length === current.length && unique.every((name, index) => name === current[index])
        ? current
        : unique
    ))
    void findRelationships('append_join', unique)
  }

  async function findRelationships(
    _nextMode: 'append_join' = 'append_join',
    requestedAppendSheets?: string[],
  ) {
    if (!file || !sheetManifest || detecting) return
    setMode('append_join')
    setDetecting(true)
    setRelationMessage(null)
    try {
      const requested = requestedAppendSheets ?? appendSheets
      const retainedAppendSelection = compatibleSheets.filter((name) => requested.includes(name))
      const appendSelection = retainedAppendSelection.length >= 1
        ? retainedAppendSelection
        : compatibleSheets
      const focus = { sheets: appendSelection }
      const datasetKey = datasetId ?? storagePath ?? `${file.name}:${file.size}:${file.lastModified}`
      const cacheKey = `${datasetKey}|${JSON.stringify(sheetManifest)}|${JSON.stringify(focus)}`
      let response = getCachedRelationships(cacheKey)
      if (!response) {
        response = await apiPost<RelationshipResult>(
          '/sheets/relationships',
          buildDatasetForm(file, storagePath, {
            manifest: JSON.stringify(sheetManifest),
            ...(datasetId ? { dataset_id: datasetId } : {}),
            focus: JSON.stringify(focus),
          }),
        )
        cacheRelationships(cacheKey, response)
      }
      const costSelection = selectAppendJoinCostCandidates(response.candidates, appendSelection)
      setCandidates(costSelection.candidates)
      const recommended = costSelection.automatic ?? null
      if (recommended && appendSelection.length >= 1) {
        setAppendSheets((current) => (
          appendSelection.length === current.length &&
          appendSelection.every((name, index) => name === current[index])
            ? current
            : appendSelection
        ))
        setSheet(recommended.left_sheet)
        const nextScope: AnalysisScope = response.analysis_scope?.mode === 'append_join'
          ? response.analysis_scope
          : {
              mode: 'append_join',
              sheets: [...new Set([...appendSelection, recommended.right_sheet])],
              append_sheets: appendSelection,
              active_sheet: recommended.left_sheet,
              join: {
                left_sheet: recommended.left_sheet,
                right_sheet: recommended.right_sheet,
                left_keys: recommended.left_keys,
                right_keys: recommended.right_keys,
                type: 'left',
              },
            }
        setAnalysisScope(nextScope)
        if (
          response.metrics &&
          JSON.stringify(response.metrics.analysis_scope ?? null) === JSON.stringify(nextScope)
        ) {
          setMetrics(response.metrics)
        }
        setRelationMessage(
          `Listo: analizamos ${appendSelection.length} hojas de ventas como un solo periodo y vinculamos los costos de ${recommended.right_sheet} usando ${recommended.left_keys.join(' + ')}.`,
        )
      } else {
        // No conservar detrás de este diagnóstico un alcance anterior que
        // afirmaba haber agregado costos.
        if (analysisScope?.mode === 'append_join') setAnalysisScope(null)
        const explanation = costSelection.blocked ?? costSelection.candidates[0]
        setRelationMessage(
          explanation
            ? relationshipPlainMessage(explanation)
            : response.candidates.length > 0
              ? 'No encontramos una relación de costos recomendada. Las conexiones con Clientes, Sucursales u otras tablas están disponibles en “Relación manual”.'
              : response.message ?? 'No encontramos una hoja de costos segura.',
        )
      }
    } catch (err) {
      setCandidates([])
      setRelationMessage(err instanceof ApiError ? err.message : 'No pudimos revisar las conexiones.')
    } finally {
      setDetecting(false)
    }
  }

  const selectMode = (next: Mode) => {
    if (detecting || (next !== 'single' && pendingSelectedCount > 0)) return
    manualModeSelected.current = true
    setMode(next)
    if (next === 'single') chooseSingle(sheet && cleanedSheets.includes(sheet) ? sheet : cleanedSheets[0])
    if (next === 'append') chooseAppend(compatibleSheets)
    if (next === 'append_join') void findRelationships('append_join')
    // 'join' (Relación manual) abre el workspace de relaciones, que detecta el
    // catálogo, permite elegir una relación y calcula su dashboard.
  }

  const confirmRelation = (candidate: RelationshipCandidate) => {
    setSheet(candidate.left_sheet)
    const retained = compatibleSheets.filter((name) => appendSheets.includes(name))
    const appendSelection = retained.length >= 1 ? retained : compatibleSheets
    if (appendSelection.length < 1 || !appendSelection.includes(candidate.left_sheet)) {
      setRelationMessage('Selecciona al menos una hoja de ventas que use la clave validada.')
      return
    }
    setAnalysisScope({
      mode: 'append_join',
      sheets: [...new Set([...appendSelection, candidate.right_sheet])],
      append_sheets: appendSelection,
      active_sheet: candidate.left_sheet,
      join: {
        left_sheet: candidate.left_sheet,
        right_sheet: candidate.right_sheet,
        left_keys: candidate.left_keys,
        right_keys: candidate.right_keys,
        type: 'left',
      },
    })
  }

  const disabledModes: Partial<Record<Mode, string>> = pendingSelectedCount > 0
    ? {
        append: 'Espera a que termine la limpieza de todas las hojas seleccionadas.',
        append_join: 'Espera a que termine la limpieza de todas las hojas seleccionadas.',
        join: 'Espera a que termine la limpieza de todas las hojas seleccionadas.',
      }
    : {}

  return (
    <section
      className="@container -mt-5 mb-6 rounded-2xl border border-navy/10 bg-white p-3 shadow-[0_12px_35px_rgba(13,43,66,0.08)] sm:p-4"
      aria-label="Datos que estas analizando"
    >
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-teal/10">
            <Link2 className="h-4 w-4 text-teal" />
          </span>
          <h2 className="text-xs font-semibold text-navy/75">Datos que estas analizando</h2>
          {selectedSheets.length <= 1 && (
            <Link
              to="/estandarizacion"
              className="ml-auto inline-flex min-h-11 items-center justify-center rounded-xl border border-orange-200 bg-orange-50 px-4 text-xs font-semibold text-orange-700 hover:bg-orange-100"
            >
              Administrar hojas
            </Link>
          )}
        </div>
        {selectedSheets.length > 1 && (
          <div className="min-w-0">
            <AnalysisModeSwitcher
              mode={mode}
              onSelect={selectMode}
              disabledModes={disabledModes}
              busy={detecting}
            />
          </div>
        )}
      </div>

      {pendingSelectedCount > 0 && (
        <p className="mt-2 flex items-center gap-2 rounded-lg bg-gold/10 px-3 py-2 text-xs text-navy/70">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-gold" />
          Faltan {pendingSelectedCount} hoja(s) por limpiar. Puedes revisar una hoja, pero el análisis combinado se habilitará al terminar.
        </p>
      )}

      {mode === 'single' && (
        cleanedSheets.length === 1 ? (
          <p className="mt-3 text-xs text-navy/60">
            Hoja activa: <strong className="font-semibold text-navy">{activeCleanedSheet}</strong>
          </p>
        ) : (
          <label className="mt-3 flex flex-wrap items-center gap-2 text-xs text-navy/60">
            Hoja
            <select
              value={
                analysisScope?.mode === 'single' &&
                cleanedSheets.includes(analysisScope.active_sheet)
                  ? analysisScope.active_sheet
                  : activeCleanedSheet
              }
              onChange={(event) => chooseSingle(event.target.value)}
              className="rounded-md border border-navy/20 bg-white px-2.5 py-1.5 font-semibold text-navy outline-none focus:border-teal"
            >
              {cleanedSheets.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
        )
      )}

      {mode === 'append' && (
        <div className="mt-3">
          <p className="text-xs text-navy/55">Esta opción solo junta filas y agrega hoja_origen; no incorpora costos de Productos.</p>
          <div className="mt-2 flex flex-wrap gap-3">
            {compatibleSheets.map((name) => (
              <label key={name} className="flex items-center gap-1.5 text-xs text-navy/70">
                <input
                  type="checkbox"
                  checked={appendSheets.includes(name)}
                  onChange={(event) => chooseAppend(
                    event.target.checked
                      ? [...appendSheets, name]
                      : appendSheets.filter((item) => item !== name),
                  )}
                  className="h-4 w-4 accent-teal"
                />
                {name}
              </label>
            ))}
          </div>
          {appendSheets.length < 2 && (
            <p className="mt-2 text-xs text-coral">
              No hay al menos dos hojas con la misma estructura para combinar.
            </p>
          )}
        </div>
      )}

      {mode === 'append_join' && (
        <div className="mt-3 rounded-lg border border-navy/10 bg-white p-3">
          <div className="mb-3 border-b border-navy/10 pb-3">
            <p className="text-xs text-navy/55">Buscamos automáticamente una clave común (por ejemplo SKU o ID), apilamos las ventas compatibles y agregamos los costos sin cambiar filas ni ingresos. No necesitas elegir columnas.</p>
            <p className="mt-2 text-xs font-semibold text-navy">Cambiar hojas de ventas</p>
            <div className="mt-2 flex flex-wrap gap-3">
              {compatibleSheets.map((name) => (
                <label key={name} className="flex items-center gap-1.5 text-xs text-navy/70">
                  <input
                    type="checkbox"
                    checked={appendSheets.includes(name)}
                    disabled={detecting}
                    title={detecting ? 'Espera a que termine la validación de la selección.' : undefined}
                    onChange={(event) => chooseAppendJoin(
                      event.target.checked
                        ? [...appendSheets, name]
                        : appendSheets.filter((item) => item !== name),
                    )}
                    className="h-4 w-4 accent-teal disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  {name}
                </label>
              ))}
            </div>
          </div>
          {detecting ? (
            <p className="flex items-center gap-2 text-xs text-navy/60">
              <Loader2 className="h-4 w-4 animate-spin text-teal" /> Buscando conexiones seguras...
            </p>
          ) : activeAppendJoin ? (
            <div className="rounded-lg border border-green/25 bg-green/[0.07] p-3">
              <div className="flex items-start gap-2.5">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-navy">Ventas + costos activo</p>
                  <p className="mt-1 text-sm font-semibold text-navy">
                    {activeAppendJoin.append_sheets.length === 1
                      ? activeAppendJoin.append_sheets[0]
                      : `${activeAppendJoin.append_sheets.length} hojas de ventas combinadas`}
                    {' ↔ '}{activeAppendJoin.join.right_sheet}
                  </p>
                  <p className="mt-0.5 text-xs text-navy/60">
                    Clave: {activeAppendJoin.join.left_keys.join(' + ')} ↔{' '}
                    {activeAppendJoin.join.right_keys.join(' + ')}
                  </p>
                  {(activeRows !== null || unmatchedRows !== null) && (
                    <p className="mt-1 text-[11px] text-navy/55">
                      {activeRows !== null ? `${activeRows.toLocaleString('es-CL')} filas` : null}
                      {activeRows !== null && unmatchedRows !== null ? ' · ' : null}
                      {unmatchedRows !== null
                        ? `${unmatchedRows.toLocaleString('es-CL')} ventas sin correspondencia`
                        : null}
                    </p>
                  )}
                  <p className="mt-1 text-[11px] text-navy/55">
                    Los ingresos y el número de filas no cambiarán por agregar los costos.
                  </p>
                  {activeRelationCandidate && (
                    <p className="mt-1 text-[11px] text-navy/50">
                      {relationshipPlainMessage(activeRelationCandidate)}
                    </p>
                  )}
                  <div className="mt-3 flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        if (activeAppendJoin.append_sheets.length >= 2) {
                          setMode('append')
                          chooseAppend(activeAppendJoin.append_sheets)
                        } else {
                          setMode('single')
                          chooseSingle(activeAppendJoin.append_sheets[0])
                        }
                      }}
                      className="text-xs font-semibold text-teal hover:underline"
                    >
                      Desactivar costos
                    </button>
                    <button
                      type="button"
                      onClick={() => selectMode('join')}
                      className="text-xs font-semibold text-navy/60 hover:text-navy"
                    >
                      La conexión detectada no corresponde
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : candidates.length > 0 ? (
            <div className="space-y-3">
              {candidates.slice(0, advanced ? 5 : 1).map((candidate) => (
                <div key={`${candidate.left_sheet}-${candidate.right_sheet}-${candidate.left_keys.join('|')}`} className="flex flex-wrap items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-navy">
                      {candidate.recommended ? 'Conexión recomendada' : 'Conexión disponible'}:{' '}
                      {appendSheets.length > 1
                        ? `${appendSheets.length} hojas de ventas combinadas ↔ ${candidate.right_sheet}`
                        : `${candidate.left_sheet} ↔ ${candidate.right_sheet}`}
                    </p>
                    <p className="mt-0.5 text-xs text-navy/55">
                      {candidate.left_keys.join(' + ')} ↔ {candidate.right_keys.join(' + ')}
                    </p>
                    <p className="mt-1 text-[11px] text-navy/55">
                      {relationshipPlainMessage(candidate)}
                    </p>
                  </div>
                  <button type="button" onClick={() => confirmRelation(candidate)} className="rounded-lg bg-teal px-3 py-2 text-xs font-semibold text-white">
                    Apilar y relacionar
                  </button>
                  <button type="button" onClick={() => selectMode('single')} className="text-xs font-semibold text-navy/55 hover:text-navy">
                    Analizar por separado
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="flex items-start gap-2 text-xs text-navy/60">
              <AlertTriangle className="h-4 w-4 shrink-0 text-gold" />
              {relationMessage ?? 'No encontramos una conexion segura entre estas hojas. Puedes analizarlas por separado.'}
            </p>
          )}
        </div>
      )}
    </section>
  )
}
