/** Aviso de plan requerido (Fase 8).
 *
 * Cuando el usuario intenta usar una función de un plan superior, se le
 * muestra un aviso amable con CTA directa a la página Planes. Uso:
 *
 *   <PlanUpsell planNeeded="Analista" feature="descargar tu base limpia" />
 *
 * O el hook `usePlanNotice` para dispararlo desde un botón (toast inline).
 */

import { Link } from 'react-router-dom'
import { Crown, Lock, X } from 'lucide-react'

/** Fase 13: panel modal para cuentas SIN plan que intentan subir archivos.
 * Aparece cada vez que lo intentan; el CTA lleva directo a Planes. */
export function PlanRequiredModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-deep/50 p-4"
      onClick={onClose}
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
        <h2 className="mt-3 text-base font-semibold text-navy">Necesitas un plan activo</h2>
        <p className="mt-1.5 text-sm leading-relaxed text-navy/60">
          Para subir y procesar tus archivos, contrata uno de nuestros planes. El Plan
          Básico incluye estandarización, limpieza y tu dashboard de indicadores.
        </p>
        <Link
          to="/planes"
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-gold px-5 py-2.5 text-sm font-semibold text-navy-deep transition-colors hover:bg-gold/90"
        >
          <Crown className="h-4 w-4" /> Ir a Planes
        </Link>
        <button
          onClick={onClose}
          className="mt-2 block w-full text-xs font-medium text-navy/50 transition-colors hover:text-navy"
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
