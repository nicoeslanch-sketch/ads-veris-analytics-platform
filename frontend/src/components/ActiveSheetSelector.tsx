import { AlertTriangle, Layers3, Link2, Loader2, Rows3 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDataset } from '../data/DatasetContext'
import { ApiError, apiPost, buildDatasetForm } from '../lib/api'
import type { AnalysisScope, RelationshipCandidate, RelationshipResult } from '../lib/types'
import { usePlan } from '../lib/usePlan'

type Mode = AnalysisScope['mode']

export default function ActiveSheetSelector() {
  const {
    file,
    storagePath,
    sheet,
    availableSheets,
    selectedSheets,
    sheetSessions,
    sheetManifest,
    analysisScope,
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
    const base = cleanedSheets[0]
    if (!base) return []
    const baseColumns = sheetSessions[base]?.cleaning?.preview.columnas ?? []
    const signature = [...baseColumns].sort().join('\u0000')
    return cleanedSheets.filter((name) => {
      const columns = sheetSessions[name]?.cleaning?.preview.columnas ?? []
      return [...columns].sort().join('\u0000') === signature
    })
  }, [cleanedSheets, sheetSessions])
  const [mode, setMode] = useState<Mode>(analysisScope?.mode ?? 'single')
  const [appendSheets, setAppendSheets] = useState<string[]>(
    analysisScope?.mode === 'append' ? analysisScope.sheets : compatibleSheets,
  )
  const [candidates, setCandidates] = useState<RelationshipCandidate[]>([])
  const [relationMessage, setRelationMessage] = useState<string | null>(null)
  const [detecting, setDetecting] = useState(false)

  useEffect(() => {
    if (analysisScope) setMode(analysisScope.mode)
  }, [analysisScope])

  if (!file || cleanedSheets.length <= 1) return null

  const chooseSingle = (name: string) => {
    setSheet(name)
    setAnalysisScope({ mode: 'single', sheets: [name], active_sheet: name })
  }

  const chooseAppend = (names: string[]) => {
    const unique = compatibleSheets.filter((name) => names.includes(name))
    setAppendSheets(unique)
    if (unique.length >= 2) {
      setAnalysisScope({ mode: 'append', sheets: unique, active_sheet: unique[0] })
    }
  }

  const findRelationships = async () => {
    if (!sheetManifest) return
    setMode('join')
    setDetecting(true)
    setRelationMessage(null)
    try {
      const response = await apiPost<RelationshipResult>(
        '/sheets/relationships',
        buildDatasetForm(file, storagePath, { manifest: JSON.stringify(sheetManifest) }),
      )
      setCandidates(response.candidates.filter((candidate) => candidate.safe))
      setRelationMessage(response.message)
    } catch (err) {
      setCandidates([])
      setRelationMessage(err instanceof ApiError ? err.message : 'No pudimos revisar las conexiones.')
    } finally {
      setDetecting(false)
    }
  }

  const selectMode = (next: Mode) => {
    setMode(next)
    if (next === 'single') chooseSingle(sheet && cleanedSheets.includes(sheet) ? sheet : cleanedSheets[0])
    if (next === 'append') chooseAppend(compatibleSheets)
    if (next === 'join') void findRelationships()
  }

  const confirmRelation = (candidate: RelationshipCandidate) => {
    setSheet(candidate.left_sheet)
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
            ['single', 'Una hoja', Layers3],
            ['append', 'Varias compatibles', Rows3],
            ['join', 'Hojas relacionadas', Link2],
          ] as const).map(([value, label, Icon]) => (
            <button
              key={value}
              type="button"
              onClick={() => selectMode(value)}
              className={`inline-flex min-w-max items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold ${mode === value ? 'bg-teal text-white' : 'text-navy/60 hover:bg-navy/5'}`}
            >
              <Icon className="h-3.5 w-3.5" /> {label}
            </button>
          ))}
        </div>
        <Link to="/estandarizacion" className="ml-auto text-xs font-semibold text-teal hover:underline">
          Administrar hojas
        </Link>
      </div>

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
          <p className="text-xs text-navy/55">Apilaremos las filas y agregaremos la columna hoja_origen.</p>
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

      {mode === 'join' && (
        <div className="mt-3 rounded-lg border border-navy/10 bg-white p-3">
          {detecting ? (
            <p className="flex items-center gap-2 text-xs text-navy/60">
              <Loader2 className="h-4 w-4 animate-spin text-teal" /> Buscando conexiones seguras...
            </p>
          ) : candidates.length > 0 ? (
            <div className="space-y-3">
              {candidates.slice(0, advanced ? 5 : 1).map((candidate) => (
                <div key={`${candidate.left_sheet}-${candidate.right_sheet}-${candidate.left_keys.join('|')}`} className="flex flex-wrap items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-navy">
                      Encontramos una conexion entre {candidate.left_sheet} y {candidate.right_sheet}
                    </p>
                    <p className="mt-0.5 text-xs text-navy/55">
                      {candidate.left_keys.join(' + ')} ↔ {candidate.right_keys.join(' + ')}
                    </p>
                    {advanced && (
                      <p className="mt-1 text-[11px] text-navy/45">
                        {candidate.cardinality} · cobertura {Math.round(candidate.coverage_left * 100)}% · solapamiento {Math.round(candidate.overlap * 100)}%
                      </p>
                    )}
                  </div>
                  <button type="button" onClick={() => confirmRelation(candidate)} className="rounded-lg bg-teal px-3 py-2 text-xs font-semibold text-white">
                    Usar esta conexion
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
