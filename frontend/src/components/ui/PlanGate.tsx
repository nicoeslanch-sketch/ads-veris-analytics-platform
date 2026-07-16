/** Aviso de plan requerido (Fase 8).
 *
 * Cuando el usuario intenta usar una función de un plan superior, se le
 * muestra un aviso amable con CTA directa a la página Planes. Uso:
 *
 *   <PlanUpsell planNeeded="Analista" feature="descargar tu base limpia" />
 *
 * O el hook `usePlanNotice` para dispararlo desde un botón (toast inline).
 */

import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Crown, Eye, Lock, Sparkles, X } from 'lucide-react'
import { useAccess } from '../../lib/access'
import { useDemo } from '../../demo/DemoContext'
import { TrialModal } from '../trial/TrialModal'

/** Fase 13/14: panel modal comercial para cuentas SIN acceso de procesamiento.
 * Es la interceptación COMPACTA que aparece ANTES del selector de archivos,
 * del drag & drop y de cualquier llamada a la API. Tres estados:
 *  - sin plan y sin prueba usada → activar prueba gratuita / Planes / demo;
 *  - prueba expirada → Planes / demo;
 *  - (con prueba vigente o plan, este modal nunca se abre). */
export function PlanRequiredModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { access } = useAccess()
  const demo = useDemo()
  const navigate = useNavigate()
  const [trialOpen, setTrialOpen] = useState(false)

  // Fase 14b: cerrar con Escape (accesibilidad) + estado limpio al reabrir.
  useEffect(() => {
    if (open) setTrialOpen(false)
  }, [open])
  useEffect(() => {
    if (!open || trialOpen) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, trialOpen, onClose])

  if (!open) return null
  if (trialOpen) {
    return (
      <TrialModal
        open
        onClose={() => {
          setTrialOpen(false)
          onClose()
        }}
      />
    )
  }

  const trial = access?.trial
  const trialExpired = Boolean(trial?.used && !trial?.active)
  const canOfferTrial = Boolean(access && !access.trial.used)

  const verDemo = () => {
    demo.enter()
    onClose()
    navigate('/')
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-deep/50 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Necesitas un plan activo"
    >
      <div
        className="relative w-full max-w-sm rounded-2xl bg-white p-6 text-center shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          aria-label="Cerrar"
          className="absolute right-3 top-3 rounded-lg p-1 text-navy/40 transition-colors hover:bg-navy/5 hover:text-navy"
        >
          <X className="h-5 w-5" />
        </button>
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-gold/15">
          <Lock className="h-6 w-6 text-gold" />
        </div>
        <h2 className="mt-3 text-base font-semibold text-navy">
          {trialExpired ? 'Tu prueba gratuita terminó' : 'Necesitas un plan activo'}
        </h2>
        <p className="mt-1.5 text-sm leading-relaxed text-navy/60">
          {trialExpired
            ? 'Tus archivos siguen guardados según la retención de tu cuenta. Para seguir procesando datos, contrata uno de nuestros planes.'
            : 'Para subir y procesar tus archivos, contrata uno de nuestros planes o activa la prueba gratuita de 15 días. El Plan Básico incluye estandarización, limpieza, dashboard y asistente IA.'}
        </p>
        {canOfferTrial && !trialExpired && (
          <button
            onClick={() => setTrialOpen(true)}
            className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gold px-5 py-2.5 text-sm font-semibold text-navy-deep transition-colors hover:bg-gold/90"
          >
            <Sparkles className="h-4 w-4" /> Probar demo gratuita (15 días)
          </button>
        )}
        <Link
          to="/planes"
          onClick={onClose}
          className={`mt-2 inline-flex w-full items-center justify-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold transition-colors ${
            canOfferTrial && !trialExpired
              ? 'border border-navy/20 text-navy hover:border-gold/60 hover:text-navy'
              : 'bg-gold text-navy-deep hover:bg-gold/90'
          }`}
        >
          <Crown className="h-4 w-4" /> Ir a Planes
        </Link>
        <button
          onClick={verDemo}
          className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-lg px-5 py-2 text-xs font-semibold text-teal transition-colors hover:bg-teal/5"
        >
          <Eye className="h-3.5 w-3.5" /> Ver demo ficticia
        </button>
        <button
          onClick={onClose}
          className="mt-1 block w-full text-xs font-medium text-navy/50 transition-colors hover:text-navy"
        >
          Ahora no
        </button>
      </div>
    </div>
  )
}

export function PlanUpsell({
  planNeeded,
  feature,
  compact = false,
}: {
  planNeeded: string
  feature: string
  compact?: boolean
}) {
  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gold/40 bg-gradient-to-r from-gold/10 to-transparent px-4 py-2.5">
        <Lock className="h-4 w-4 shrink-0 text-gold" />
        <p className="flex-1 text-sm text-navy/75">
          Necesitas el <strong>Plan {planNeeded}</strong> para {feature}.
        </p>
        <Link
          to="/planes"
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-gold px-3.5 py-1.5 text-xs font-semibold text-navy-deep transition-colors hover:bg-gold/90"
        >
          <Crown className="h-3.5 w-3.5" /> Ir a comprar el plan
        </Link>
      </div>
    )
  }
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-gold/50 bg-gradient-to-b from-gold/10 to-transparent px-6 py-8 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-gold/15">
        <Lock className="h-5 w-5 text-gold" />
      </div>
      <div>
        <p className="text-sm font-semibold text-navy">
          Necesitas el Plan {planNeeded}
        </p>
        <p className="mt-1 text-xs text-navy/60">
          Para {feature} contrata el Plan {planNeeded} o uno superior.
        </p>
      </div>
      <Link
        to="/planes"
        className="inline-flex items-center gap-2 rounded-lg bg-gold px-5 py-2 text-sm font-semibold text-navy-deep transition-colors hover:bg-gold/90"
      >
        <Crown className="h-4 w-4" /> Ir a comprar el plan
      </Link>
    </div>
  )
}
