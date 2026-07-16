/** Piezas visuales de la demo ficticia (Fase 14).
 *
 * DemoBanner — etiqueta PERSISTENTE mientras la demo está activa (se monta en
 * AppShell, sobre el contenido): deja claro que TODO lo visible es ficticio,
 * y ofrece salir o activar la prueba gratuita.
 *
 * DemoEmptyActions — botones para los estados vacíos de Resumen, Explorar y
 * Limpieza: "Ver demo ficticia" (siempre) y "Probar demo gratuita (15 días)"
 * (solo cuentas sin plan que no han usado su prueba — a un cliente con plan
 * no se le ofrece una prueba).
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Eye, FlaskConical, Sparkles, X } from 'lucide-react'
import { useAccess } from '../lib/access'
import { DEMO_COMPANY, DEMO_LABEL, useDemo } from './DemoContext'
import { TrialModal } from '../components/trial/TrialModal'

export function DemoBanner() {
  const demo = useDemo()
  const { access } = useAccess()
  const [trialOpen, setTrialOpen] = useState(false)

  if (!demo.active) return null
  const canOfferTrial = Boolean(access && !access.trial.used && access.paid_plan === 'sin_plan' && !access.is_admin)

  return (
    <>
      <TrialModal open={trialOpen} onClose={() => setTrialOpen(false)} />
      <div
        role="status"
        className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-gold/50 bg-gold/10 px-4 py-3"
      >
        <FlaskConical className="h-5 w-5 shrink-0 text-gold" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-navy">{DEMO_LABEL}</p>
          <p className="text-xs text-navy/60">
            Estás viendo a {DEMO_COMPANY}: nada de esto es tuyo ni se guarda en tu
            cuenta. Así se ve la plataforma con datos reales de un negocio.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {canOfferTrial && (
            <button
              onClick={() => setTrialOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-gold px-3.5 py-2 text-xs font-semibold text-navy-deep transition-colors hover:bg-gold/90"
            >
              <Sparkles className="h-3.5 w-3.5" /> Probar demo gratuita (15 días)
            </button>
          )}
          <button
            onClick={demo.exit}
            className="inline-flex items-center gap-1.5 rounded-lg border border-navy/20 bg-white px-3.5 py-2 text-xs font-semibold text-navy transition-colors hover:bg-navy/5"
          >
            <X className="h-3.5 w-3.5" /> Salir de la demo
          </button>
        </div>
      </div>
    </>
  )
}

export function DemoEmptyActions() {
  const demo = useDemo()
  const { access } = useAccess()
  const navigate = useNavigate()
  const [trialOpen, setTrialOpen] = useState(false)

  const canOfferTrial = Boolean(access && !access.trial.used && access.paid_plan === 'sin_plan' && !access.is_admin)

  return (
    <div className="flex flex-col items-center gap-2 sm:flex-row">
      <TrialModal open={trialOpen} onClose={() => setTrialOpen(false)} />
      <button
        onClick={() => {
          demo.enter()
          navigate('/')
        }}
        className="inline-flex items-center gap-2 rounded-lg border border-teal/50 px-4 py-2 text-xs font-semibold text-teal transition-colors hover:bg-teal hover:text-white"
      >
        <Eye className="h-3.5 w-3.5" /> Ver demo ficticia
      </button>
      {canOfferTrial && (
        <button
          onClick={() => setTrialOpen(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-gold px-4 py-2 text-xs font-semibold text-navy-deep transition-colors hover:bg-gold/90"
        >
          <Sparkles className="h-3.5 w-3.5" /> Probar demo gratuita (15 días)
        </button>
      )}
    </div>
  )
}
