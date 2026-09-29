import { LEGAL_VERSION } from '../lib/privacy'

export default function LegalConsent({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return <label className="flex items-start gap-3 text-sm leading-relaxed text-navy/80">
    <input type="checkbox" required checked={checked} onChange={e => onChange(e.target.checked)}
      className="mt-1 h-4 w-4 shrink-0 accent-teal" />
    <span>Acepto las <a className="font-medium text-teal underline" href="/condiciones" target="_blank" rel="noopener noreferrer">condiciones de uso</a> y autorizo
      el tratamiento de mis datos de cuenta para prestar el servicio y atender mis solicitudes,
      conforme a la <a className="font-medium text-teal underline" href="/privacidad" target="_blank" rel="noopener noreferrer">politica de privacidad</a>.
      No incluye publicidad. Puedo revocar esta autorizacion. Version {LEGAL_VERSION}.</span>
  </label>
}
