import { AlertTriangle, CheckCircle2, Layers3, Link2, Loader2, Rows3 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDataset } from '../data/DatasetContext'
import { ApiError, apiPost, buildDatasetForm } from '../lib/api'
import { cacheRelationships, getCachedRelationships } from '../lib/analysisCache'
import {
  compatibleAppendSheets,
  relationshipPlainMessage,
  selectAppendJoinCostCandidates,
} from '../lib/multiSheet'
import type { AnalysisScope, RelationshipCandidate, RelationshipResult } from '../lib/types'
import { usePlan } from '../lib/usePlan'

type Mode = AnalysisScope['mode']

export default function ActiveSheetSelector() {
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
    setAnalysisScope,
    setSheet,
  } = useDataset()
  const { plan } = usePlan()
  const advanced = plan === 'analista' || plan === 'gold'
  const cleanedSheets = useMemo(
    () => availableSheets.filter(
      (name) => selectedSheets.includes(name) && Boolean(sheetSessions[name]?.cleaning),
    ),
    [availableSheets, selectedSheets, sheetSessions],
  )
  const compatibleSheets = useMemo(() => {
    return compatibleAppendSheets(
      cleanedSheets,
      Object.fromEntries(cleanedSheets.map((name) => [name, sheetSessions[name]?.cleaning])),
    )
  }, [cleanedSheets, sheetSessions])
  const pendingSelectedCount = selectedSheets.filter(
    (name) => !sheetSessions[name]?.cleaning,
  ).length
  const [mode, setMode] = useState<Mode>(analysisScope?.mode ?? 'single')
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
  const [manualLeft, setManualLeft] = useState(cleanedSheets[0] ?? '')
  const [manualRight, setManualRight] = useState(cleanedSheets[1] ?? '')
  const [manualLeftKeys, setManualLeftKeys] = useState<string[]>(['', ''])
  const [manualRightKeys, setManualRightKeys] = useState<string[]>(['', ''])
  const [showAdvanced, setShowAdvanced] = useState(false)

  useEffect(() => {
    if (analysisScope) setMode(analysisScope.mode)
  }, [analysisScope])

  useEffect(() => {
    if (!cleanedSheets.includes(manualLeft)) setManualLeft(cleanedSheets[0] ?? '')
    if (!cleanedSheets.includes(manualRight) || manualRight === manualLeft) {
      setManualRight(cleanedSheets.find((name) => name !== manualLeft) ?? '')
    }
  }, [cleanedSheets, manualLeft, manualRight])

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

  useEffect(() => {
    const candidate = candidates[0]
    if (!candidate) return
    setManualLeft(candidate.left_sheet)
    setManualRight(candidate.right_sheet)
    setManualLeftKeys([candidate.left_keys[0] ?? '', candidate.left_keys[1] ?? ''])
    setManualRightKeys([candidate.right_keys[0] ?? '', candidate.right_keys[1] ?? ''])
  }, [candidates])

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

  if (!file || cleanedSheets.length <= 1) return null

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

  const findRelationships = async (
    nextMode: 'join' | 'append_join' = 'join',
    requestedAppendSheets?: string[],
  ) => {
    if (!sheetManifest || detecting) return
    setMode(nextMode)
    setDetecting(true)
    setRelationMessage(null)
    try {
      const requested = requestedAppendSheets ?? appendSheets
      const retainedAppendSelection = compatibleSheets.filter((name) => requested.includes(name))
      const appendSelection = retainedAppendSelection.length >= 1
        ? retainedAppendSelection
        : compatibleSheets
      const focus = nextMode === 'append_join' ? { sheets: appendSelection } : null
      const datasetKey = datasetId ?? storagePath ?? `${file.name}:${file.size}:${file.lastModified}`
      const cacheKey = `${datasetKey}|${JSON.stringify(sheetManifest)}|${JSON.stringify(focus)}`
      let response = getCachedRelationships(cacheKey)
      if (!response) {
        response = await apiPost<RelationshipResult>(
          '/sheets/relationships',
          buildDatasetForm(file, storagePath, {
            manifest: JSON.stringify(sheetManifest),
            ...(datasetId ? { dataset_id: datasetId } : {}),
            ...(focus ? { focus: JSON.stringify(focus) } : {}),
          }),
        )
        cacheRelationships(cacheKey, response)
      }
      const costSelection = nextMode === 'append_join'
        ? selectAppendJoinCostCandidates(response.candidates, appendSelection)
        : null
      const safeCandidates = costSelection?.candidates ?? response.candidates
        .filter((candidate) => candidate.safe)
        .sort((left, right) => Number(Boolean(right.recommended)) - Number(Boolean(left.recommended)))
      setCandidates(safeCandidates)
      const recommended = costSelection?.automatic ?? null
      if (recommended && appendSelection.length >= 1) {
        setAppendSheets((current) => (
          appendSelection.length === current.length &&
          appendSelection.every((name, index) => name === current[index])
            ? current
            : appendSelection
        ))
        setSheet(recommended.left_sheet)
        setAnalysisScope({
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
        })
        setRelationMessage(
          `Listo: apilamos ${appendSelection.length} hojas de ventas y agregamos los costos de ${recommended.right_sheet} por ${recommended.left_keys.join(' + ')}.`,
        )
      } else {
        if (nextMode === 'append_join') {
          // No conservar detrás de este diagnóstico un alcance anterior que
          // afirmaba haber agregado costos.
          if (analysisScope?.mode === 'append_join') setAnalysisScope(null)
          const explanation = costSelection?.blocked ?? costSelection?.candidates[0]
          setRelationMessage(
            explanation
              ? relationshipPlainMessage(explanation)
              : response.candidates.length > 0
                ? 'No encontramos una relación de costos recomendada. Las conexiones con Clientes, Sucursales u otras tablas están disponibles en “Relacionar otras hojas”.'
                : response.message ?? 'No encontramos una hoja de costos segura.',
          )
        } else {
          setRelationMessage(response.message)
        }
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
    setMode(next)
    if (next === 'single') chooseSingle(sheet && cleanedSheets.includes(sheet) ? sheet : cleanedSheets[0])
    if (next === 'append') chooseAppend(compatibleSheets)
    if (next === 'join' || next === 'append_join') void findRelationships(next)
  }

  const validateManualRelationship = async () => {
    if (!sheetManifest || !manualLeft || !manualRight) return
    const pairs = manualLeftKeys
      .map((leftKey, index) => [leftKey, manualRightKeys[index]] as const)
      .filter(([leftKey, rightKey]) => leftKey && rightKey)
    if (!pairs.length) {
      setRelationMessage('Elige al menos una columna en cada hoja.')
      return
    }
    setDetecting(true)
    setRelationMessage(null)
    try {
      const response = await apiPost<RelationshipResult>(
        '/sheets/relationships',
        buildDatasetForm(file, storagePath, {
          manifest: JSON.stringify(sheetManifest),
          ...(datasetId ? { dataset_id: datasetId } : {}),
          relationship: JSON.stringify({
            left_sheet: manualLeft,
            right_sheet: manualRight,
            left_keys: pairs.map(([leftKey]) => leftKey),
            right_keys: pairs.map(([, rightKey]) => rightKey),
            type: 'left',
          }),
        }),
      )
      if (response.manual?.safe) {
        setCandidates([response.manual])
        setRelationMessage(relationshipPlainMessage(response.manual))
      } else {
        setCandidates([])
        const inspected = response.manual
        setRelationMessage(
          inspected
            ? relationshipPlainMessage(inspected)
            : 'No se pudo validar la relacion.',
        )
      }
    } catch (err) {
      setRelationMessage(err instanceof ApiError ? err.message : 'No pudimos validar esas columnas.')
    } finally {
      setDetecting(false)
    }
  }

  const confirmRelation = (candidate: RelationshipCandidate) => {
    setSheet(candidate.left_sheet)
    if (mode === 'append_join') {
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
      return
    }
    setAnalysisScope({
      mode: 'join',
      sheets: [candidate.left_sheet, candidate.right_sheet],
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

  return (
    <section className="-mt-5 mb-6 border-b border-navy/10 pb-4" aria-label="Datos que estas analizando">
      <div className="flex flex-wrap items-center gap-2">
        <Layers3 className="h-4 w-4 text-teal" />
        <h2 className="text-xs font-semibold text-navy/75">Datos que estas analizando</h2>
        <div className="flex max-w-full overflow-x-auto rounded-lg border border-navy/15 bg-white p-1">
          {([
            ['single', 'Analizar una hoja', Layers3],
            ['append_join', 'Ventas + costos (recomendado)', Link2],
            ['append', 'Solo apilar ventas', Rows3],
            ['join', 'Relacionar otras hojas', Link2],
          ] as const).map(([value, label, Icon]) => (
            <button
              key={value}
              type="button"
              onClick={() => selectMode(value)}
              disabled={detecting || (value !== 'single' && pendingSelectedCount > 0)}
              title={value !== 'single' && pendingSelectedCount > 0 ? 'Espera a que termine la limpieza de todas las hojas seleccionadas.' : undefined}
              className={`inline-flex min-w-max items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-45 ${mode === value ? 'bg-teal text-white' : 'text-navy/60 hover:bg-navy/5'}`}
            >
              <Icon className="h-3.5 w-3.5" /> {label}
            </button>
          ))}
        </div>
        <Link to="/estandarizacion" className="ml-auto text-xs font-semibold text-teal hover:underline">
          Administrar hojas
        </Link>
      </div>

      {pendingSelectedCount > 0 && (
        <p className="mt-2 flex items-center gap-2 rounded-lg bg-gold/10 px-3 py-2 text-xs text-navy/70">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-gold" />
          Faltan {pendingSelectedCount} hoja(s) por limpiar. Puedes revisar una hoja, pero el análisis combinado se habilitará al terminar.
        </p>
      )}

      {mode === 'single' && (
        <label className="mt-3 flex flex-wrap items-center gap-2 text-xs text-navy/60">
          Hoja
          <select
            value={analysisScope?.mode === 'single' ? analysisScope.active_sheet : (sheet ?? cleanedSheets[0])}
            onChange={(event) => chooseSingle(event.target.value)}
            className="rounded-md border border-navy/20 bg-white px-2.5 py-1.5 font-semibold text-navy outline-none focus:border-teal"
          >
            {cleanedSheets.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
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

      {(mode === 'join' || mode === 'append_join') && (
        <div className="mt-3 rounded-lg border border-navy/10 bg-white p-3">
          {mode === 'append_join' && (
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
          )}
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
                      onClick={() => {
                        setShowAdvanced(true)
                        selectMode('join')
                      }}
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
                      {mode === 'append_join' && appendSheets.length > 1
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
                    {mode === 'append_join' ? 'Apilar y relacionar' : 'Usar esta conexion'}
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
          {(mode === 'join' || showAdvanced) && <details className="mt-3 border-t border-navy/10 pt-3" open={showAdvanced}>
            <summary className="cursor-pointer text-xs font-semibold text-teal">
              Opciones avanzadas: elegir columnas manualmente
            </summary>
            <p className="mt-1 text-[11px] text-navy/50">
              Úsalo solo si la conexión automática no corresponde. Comprobaremos que la llave exista y que la unión no multiplique ventas.
            </p>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {([0, 1] as const).map((index) => (
                <div key={index} className="contents">
                  <label className="text-[11px] text-navy/55">
                    {index === 0 ? 'Clave principal izquierda' : 'Segunda clave izquierda (opcional)'}
                    <select
                      value={index === 0 ? manualLeft : manualLeft}
                      onChange={(event) => index === 0 && setManualLeft(event.target.value)}
                      className={`${index === 0 ? '' : 'hidden'} mt-1 w-full rounded-md border border-navy/20 px-2 py-1.5 text-xs text-navy`}
                    >
                      {cleanedSheets.map((name) => <option key={name} value={name}>{name}</option>)}
                    </select>
                    <select
                      value={manualLeftKeys[index]}
                      onChange={(event) => setManualLeftKeys((current) => current.map((value, keyIndex) => keyIndex === index ? event.target.value : value))}
                      className="mt-1 w-full rounded-md border border-navy/20 px-2 py-1.5 text-xs text-navy"
                    >
                      <option value="">{index === 0 ? 'Selecciona columna' : 'Sin segunda clave'}</option>
                      {(sheetSessions[manualLeft]?.cleaning?.preview.columnas ?? []).map((column) => <option key={column} value={column}>{column}</option>)}
                    </select>
                  </label>
                  <label className="text-[11px] text-navy/55">
                    {index === 0 ? 'Clave principal derecha' : 'Segunda clave derecha (opcional)'}
                    <select
                      value={manualRight}
                      onChange={(event) => index === 0 && setManualRight(event.target.value)}
                      className={`${index === 0 ? '' : 'hidden'} mt-1 w-full rounded-md border border-navy/20 px-2 py-1.5 text-xs text-navy`}
                    >
                      {cleanedSheets.filter((name) => name !== manualLeft).map((name) => <option key={name} value={name}>{name}</option>)}
                    </select>
                    <select
                      value={manualRightKeys[index]}
                      onChange={(event) => setManualRightKeys((current) => current.map((value, keyIndex) => keyIndex === index ? event.target.value : value))}
                      className="mt-1 w-full rounded-md border border-navy/20 px-2 py-1.5 text-xs text-navy"
                    >
                      <option value="">{index === 0 ? 'Selecciona columna' : 'Sin segunda clave'}</option>
                      {(sheetSessions[manualRight]?.cleaning?.preview.columnas ?? []).map((column) => <option key={column} value={column}>{column}</option>)}
                    </select>
                  </label>
                </div>
              ))}
            </div>
            <button type="button" onClick={() => void validateManualRelationship()} disabled={detecting} className="mt-3 rounded-lg border border-teal/40 px-3 py-2 text-xs font-semibold text-teal disabled:opacity-50">
              Validar relacion
            </button>
          </details>}
        </div>
      )}
    </section>
  )
}
