import { HelpCircle } from 'lucide-react'
import type { RelationshipKpi } from '../../lib/types'
import { formatKpiValue } from '../../lib/relationshipDashboard'

const TONE_ACCENT: Record<NonNullable<RelationshipKpi['tone']>, string> = {
  default: '#00a8a8',
  positive: '#2fae7d',
  warning: '#d4af37',
  risk: '#e8785a',
}

interface RelationshipKpisProps {
  kpis: RelationshipKpi[]
  currency: string
}

/** Rejilla de KPIs. Los no disponibles se muestran como "No disponible" en
 * lugar de ocultarse, para que el usuario sepa qué insumo falta. */
export default function RelationshipKpis({ kpis, currency }: RelationshipKpisProps) {
  if (!kpis.length) return null
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {kpis.map((kpi) => {
        const accent = TONE_ACCENT[kpi.tone ?? 'default']
        return (
          <div
            key={kpi.id}
            className="rounded-xl border border-navy/10 bg-white p-4 shadow-sm"
            style={{ background: `linear-gradient(135deg, ${accent}0d, #ffffff 60%)` }}
          >
            <div className="flex items-center gap-1.5">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-navy/50">
                {kpi.label}
              </p>
              {kpi.help && (
                <span title={kpi.help} className="text-navy/30">
                  <HelpCircle className="h-3 w-3" aria-hidden />
                  <span className="sr-only">{kpi.help}</span>
                </span>
              )}
            </div>
            <p
              className={`mt-1.5 text-xl font-bold ${kpi.available ? 'text-navy' : 'text-navy/35'}`}
            >
              {formatKpiValue(kpi.value, kpi.format, currency)}
            </p>
          </div>
        )
      })}
    </div>
  )
}
