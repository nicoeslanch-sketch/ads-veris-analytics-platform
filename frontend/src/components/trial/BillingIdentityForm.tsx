/** Formulario de identidad de facturación — RUT empresa o responsable (Fase 14).
 *
 * Compartido entre la activación de la prueba gratuita y la contratación de
 * planes: cambia el TEXTO DE FINALIDAD según el contexto (transparencia con
 * el dato personal), no la validación. El dígito verificador se valida en
 * vivo (módulo 11, espejo del backend); la autoridad sigue siendo el servidor.
 * El RUT no se guarda aquí ni viaja en URLs — solo en el body del POST.
 */

import { useMemo, useState } from 'react'
import { AlertTriangle, Building2, CheckCircle2, ShieldCheck, UserRound } from 'lucide-react'
import { formatRut, isValidRut, normalizeRut } from '../../lib/rut'

export type RutType = 'empresa' | 'responsable'
export type BillingFormContext = 'trial' | 'contratacion'

const PURPOSE_TEXT: Record<BillingFormContext, string> = {
  trial:
    'Usaremos este RUT para validar la elegibilidad de la prueba gratuita, ' +
    'evitar activaciones repetidas y asociar la identidad responsable de la cuenta.',
  contratacion:
    'Usaremos este RUT para identificar a la empresa o persona responsable y ' +
    'gestionar la contratación y facturación del servicio.',
}

export function BillingIdentityForm({
  context,
  submitLabel,
  submitting,
  error,
  onSubmit,
}: {
  context: BillingFormContext
  submitLabel: string
  submitting: boolean
  error: string | null
  onSubmit: (rutType: RutType, rut: string) => void
}) {
  const [rutType, setRutType] = useState<RutType>('empresa')
  const [rutInput, setRutInput] = useState('')
  const [touched, setTouched] = useState(false)

  const normalized = useMemo(() => normalizeRut(rutInput), [rutInput])
  const valid = useMemo(() => isValidRut(rutInput), [rutInput])
  const showInvalid = touched && rutInput.trim().length > 0 && !valid

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (!valid || !normalized || submitting) return
    onSubmit(rutType, normalized)
  }

  return (
    <form onSubmit={handleSubmit} className="text-left">
      <fieldset>
        <legend className="text-xs font-semibold uppercase tracking-wide text-navy/50">
          ¿Qué RUT vas a usar?
        </legend>
        <div className="mt-2 grid grid-cols-2 gap-2">
          {(
            [
              { value: 'empresa', label: 'RUT de empresa', icon: Building2 },
              { value: 'responsable', label: 'RUT del responsable', icon: UserRound },
            ] as const
          ).map(({ value, label, icon: Icon }) => (
            <label
              key={value}
              className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2.5 text-xs font-semibold transition-colors ${
                rutType === value
                  ? 'border-teal bg-teal/5 text-teal'
                  : 'border-navy/20 text-navy/65 hover:border-navy/40'
              }`}
            >
              <input
                type="radio"
                name="rut_type"
                value={value}
                checked={rutType === value}
                onChange={() => setRutType(value)}
                className="sr-only"
              />
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <label className="mt-4 block">
        <span className="text-xs font-semibold uppercase tracking-wide text-navy/50">
          {rutType === 'empresa' ? 'RUT de la empresa' : 'RUT de la persona responsable'}
        </span>
        <div
          className={`mt-1.5 flex items-center gap-2 rounded-lg border bg-white px-3 py-2.5 ${
            showInvalid ? 'border-coral' : valid ? 'border-green/60' : 'border-navy/20 focus-within:border-teal'
          }`}
        >
          <input
            value={rutInput}
            onChange={(e) => setRutInput(e.target.value)}
            onBlur={() => setTouched(true)}
            placeholder="12.345.678-9"
            inputMode="text"
            autoComplete="off"
            spellCheck={false}
            aria-invalid={showInvalid}
            aria-describedby="rut-estado"
            className="w-full bg-transparent text-sm text-navy placeholder-navy/35 outline-none"
          />
          {valid && <CheckCircle2 className="h-4.5 w-4.5 shrink-0 text-green" aria-hidden />}
        </div>
        <p id="rut-estado" aria-live="polite" className="mt-1 min-h-4 text-xs">
          {valid && normalized ? (
            <span className="text-green">RUT válido: {formatRut(normalized)}</span>
          ) : showInvalid ? (
            <span className="text-coral">
              El RUT o su dígito verificador no es válido. Revísalo (ej: 12.345.678-9).
            </span>
          ) : null}
        </p>
      </label>

      {error && (
        <div className="mt-2 flex items-start gap-2 rounded-lg border border-coral/40 bg-coral/10 px-3 py-2.5 text-xs text-coral" role="alert">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>{error}</p>
        </div>
      )}

      <button
        type="submit"
        disabled={!valid || submitting}
        className="mt-4 w-full rounded-lg bg-gold px-5 py-2.5 text-sm font-semibold text-navy-deep transition-colors hover:bg-gold/90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting ? 'Activando…' : submitLabel}
      </button>

      <div className="mt-3 flex items-start gap-2 rounded-lg bg-navy/[0.04] px-3 py-2.5">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-teal" />
        <p className="text-[11px] leading-relaxed text-navy/60">
          {PURPOSE_TEXT[context]} Se almacena protegido, se muestra enmascarado
          (12.***.***-9) y no se comparte públicamente. No validamos representación
          legal con este dato. Puedes pedir su corrección o eliminación escribiendo a
          servicios@adsveris.com. Si se usó para una prueba, conservaremos únicamente
          lo necesario para impedir activaciones repetidas mientras exista esa finalidad.
        </p>
      </div>
    </form>
  )
}
