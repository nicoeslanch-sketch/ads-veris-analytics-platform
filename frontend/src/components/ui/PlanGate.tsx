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
import { Crown, Lock } from 'lucide-react'

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
