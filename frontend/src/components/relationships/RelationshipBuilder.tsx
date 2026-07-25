import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Loader2, X, XCircle } from 'lucide-react'
import type { RelationshipCandidate } from '../../lib/types'
import { relationshipPlainMessage } from '../../lib/multiSheet'
import { formatKpiValue } from '../../lib/relationshipDashboard'

export interface ManualJoinDraft {
  left_sheet: string
  right_sheet: string
  left_keys: string[]
  right_keys: string[]
}

interface RelationshipBuilderProps {
  sheets: string[]
  columnsBySheet: Record<string, string[]>
  onClose: () => void
  onValidate: (draft: ManualJoinDraft) => Promise<RelationshipCandidate | null>
  onUse: (draft: ManualJoinDraft, validation: RelationshipCandidate) => void
}

/** Panel para crear una conexión personalizada. No activa la relación sin
 * validarla antes en el backend (misma validación many-to-one del motor). */
export default function RelationshipBuilder({
  sheets,
  columnsBySheet,
  onClose,
  onValidate,
  onUse,
}: RelationshipBuilderProps) {
  const [leftSheet, setLeftSheet] = useState(sheets[0] ?? '')
  const [rightSheet, setRightSheet] = useState(sheets.find((name) => name !== sheets[0]) ?? '')
  const [leftKeys, setLeftKeys] = useState<[string, string]>(['', ''])
  const [rightKeys, setRightKeys] = useState<[string, string]>(['', ''])
  const [validating, setValidating] = useState(false)
  const [result, setResult] = useState<RelationshipCandidate | null>(null)
  const [error, setError] = useState<string | null>(null)

  const leftColumns = columnsBySheet[leftSheet] ?? []
  const rightColumns = columnsBySheet[rightSheet] ?? []
  const rightSheetOptions = useMemo(
    () => sheets.filter((name) => name !== leftSheet),
    [sheets, leftSheet],
  )

  // Al cambiar de hoja, las columnas elegidas pueden dejar de existir.
  useEffect(() => {
    setLeftKeys((keys) => keys.map((key) => (leftColumns.includes(key) ? key : '')) as [string, string])
    setResult(null)
  }, [leftSheet, leftColumns])
  useEffect(() => {
    setRightKeys((keys) => keys.map((key) => (rightColumns.includes(key) ? key : '')) as [string, string])
    setResult(null)
  }, [rightSheet, rightColumns])

  const pairs = leftKeys
    .map((key, index) => [key, rightKeys[index]] as const)
    .filter(([left, right]) => left && right)
  // No se permite una segunda clave unilateral (una sí, otra no).
  const unbalanced = leftKeys.filter(Boolean).length !== rightKeys.filter(Boolean).length
  const canValidate = Boolean(leftSheet && rightSheet && leftSheet !== rightSheet && pairs.length && !unbalanced)

  const draft = (): ManualJoinDraft => ({
    left_sheet: leftSheet,
    right_sheet: rightSheet,
    left_keys: pairs.map(([left]) => left),
    right_keys: pairs.map(([, right]) => right),
  })

  const runValidation = async () => {
    setValidating(true)
    setError(null)
    setResult(null)
    try {
      const candidate = await onValidate(draft())
      if (candidate) setResult(candidate)
      else setError('No se pudo validar la conexión con esas columnas.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No pudimos validar la conexión.')
    } finally {
      setValidating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-deep/50 p-4" role="dialog" aria-modal="true" aria-label="Crear conexión personalizada">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-navy/10 bg-white p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-bold text-navy">Crear conexión personalizada</h3>
          <button type="button" onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1 text-navy/50 hover:bg-navy/5">
            <X className="h-5 w-5" />
          </button>
        </div>

        <p className="mb-4 text-xs text-navy/60">
          Elige las hojas y las columnas que las conectan. Comprobaremos que la unión no
          multiplique las ventas antes de activarla.
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-semibold text-navy/70">
            Hoja principal
            <select
              value={leftSheet}
              onChange={(event) => setLeftSheet(event.target.value)}
              className="mt-1 w-full rounded-lg border border-navy/20 px-2.5 py-2 text-xs font-normal text-navy outline-none focus:border-teal"
            >
              {sheets.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label className="text-xs font-semibold text-navy/70">
            Hoja relacionada
            <select
              value={rightSheet}
              onChange={(event) => setRightSheet(event.target.value)}
              className="mt-1 w-full rounded-lg border border-navy/20 px-2.5 py-2 text-xs font-normal text-navy outline-none focus:border-teal"
            >
              {rightSheetOptions.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
        </div>

        <div className="mt-3 space-y-3">
          {([0, 1] as const).map((index) => (
            <div key={index} className="grid gap-3 sm:grid-cols-2">
              <label className="text-[11px] text-navy/55">
                {index === 0 ? 'Clave principal izquierda' : 'Segunda clave izquierda (opcional)'}
                <select
                  value={leftKeys[index]}
                  onChange={(event) => setLeftKeys((keys) => index === 0 ? [event.target.value, keys[1]] : [keys[0], event.target.value])}
                  className="mt-1 w-full rounded-lg border border-navy/20 px-2.5 py-2 text-xs text-navy outline-none focus:border-teal"
                >
                  <option value="">{index === 0 ? 'Selecciona columna' : 'Sin segunda clave'}</option>
                  {leftColumns.map((column) => <option key={column} value={column}>{column}</option>)}
                </select>
              </label>
              <label className="text-[11px] text-navy/55">
                {index === 0 ? 'Clave principal derecha' : 'Segunda clave derecha (opcional)'}
                <select
                  value={rightKeys[index]}
                  onChange={(event) => setRightKeys((keys) => index === 0 ? [event.target.value, keys[1]] : [keys[0], event.target.value])}
                  className="mt-1 w-full rounded-lg border border-navy/20 px-2.5 py-2 text-xs text-navy outline-none focus:border-teal"
                >
                  <option value="">{index === 0 ? 'Selecciona columna' : 'Sin segunda clave'}</option>
                  {rightColumns.map((column) => <option key={column} value={column}>{column}</option>)}
                </select>
              </label>
            </div>
          ))}
        </div>

        {unbalanced && (
          <p className="mt-2 text-[11px] text-coral">
            Una segunda clave necesita columna en ambas hojas.
          </p>
        )}

        <button
          type="button"
          onClick={() => void runValidation()}
          disabled={!canValidate || validating}
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-teal px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
        >
          {validating && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Validar conexión
        </button>

        {error && (
          <p className="mt-3 rounded-lg bg-coral/10 px-3 py-2 text-xs text-coral">{error}</p>
        )}

        {result && (
          <div className={`mt-4 rounded-xl border p-3 ${result.safe ? 'border-green/30 bg-green/[0.07]' : 'border-coral/40 bg-coral/[0.07]'}`}>
            <div className="flex items-start gap-2">
              {result.safe
                ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green" />
                : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-coral" />}
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-navy">
                  {result.safe
                    ? 'Conexión válida: esta relación no multiplica las ventas ni altera sus totales.'
                    : 'Esta conexión no se puede activar'}
                </p>
                <p className="mt-1 text-[11px] text-navy/70">{relationshipPlainMessage(result)}</p>
                <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-navy/60">
                  <div><dt className="inline font-semibold">Cobertura izq.:</dt> {formatKpiValue(result.coverage_left * 100, 'percent')}</div>
                  <div><dt className="inline font-semibold">Cobertura der.:</dt> {formatKpiValue(result.coverage_right * 100, 'percent')}</div>
                  <div><dt className="inline font-semibold">Solapamiento:</dt> {formatKpiValue(result.overlap * 100, 'percent')}</div>
                  <div><dt className="inline font-semibold">Cardinalidad:</dt> {result.cardinality.replace(/_/g, ' ')}</div>
                  <div><dt className="inline font-semibold">Filas actuales:</dt> {formatKpiValue(result.left_rows ?? 0, 'integer')}</div>
                  <div><dt className="inline font-semibold">Filas proyectadas:</dt> {formatKpiValue(result.projected_rows ?? 0, 'integer')}</div>
                  <div><dt className="inline font-semibold">Claves duplicadas der.:</dt> {formatKpiValue(result.right_duplicate_keys ?? 0, 'integer')}</div>
                  <div><dt className="inline font-semibold">Sin correspondencia:</dt> {formatKpiValue(result.unmatched_rows ?? 0, 'integer')}</div>
                </dl>
                {result.safe && (
                  <button
                    type="button"
                    onClick={() => onUse(draft(), result)}
                    className="mt-3 rounded-lg bg-teal px-4 py-2 text-xs font-semibold text-white"
                  >
                    Usar esta conexión
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
