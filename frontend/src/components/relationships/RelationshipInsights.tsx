import { AlertTriangle, CheckCircle2, Info, Lightbulb, ShieldAlert } from 'lucide-react'
import type { InsightSeverity, RelationshipAction, RelationshipInsight } from '../../lib/types'
import { formatKpiValue } from '../../lib/relationshipDashboard'

const SEVERITY_STYLE: Record<InsightSeverity, { border: string; bg: string; icon: typeof Info; color: string }> = {
  info: { border: 'border-navy/15', bg: 'bg-navy/[0.03]', icon: Info, color: 'text-navy/60' },
  success: { border: 'border-green/30', bg: 'bg-green/[0.07]', icon: CheckCircle2, color: 'text-green' },
  warning: { border: 'border-gold/40', bg: 'bg-gold/[0.08]', icon: AlertTriangle, color: 'text-gold' },
  risk: { border: 'border-coral/40', bg: 'bg-coral/[0.08]', icon: ShieldAlert, color: 'text-coral' },
}

interface RelationshipInsightsProps {
  title: string
  icon?: 'lightbulb' | 'alert'
  items: RelationshipInsight[]
  actions: RelationshipAction[]
  currency: string
  onAction?: (action: RelationshipAction) => void
}

/** Bloque de hallazgos o alertas deterministas. Cada tarjeta incluye título,
 * explicación, evidencia, impacto (solo si es calculable) y acción vinculada. */
export default function RelationshipInsights({
  title,
  icon = 'lightbulb',
  items,
  actions,
  currency,
  onAction,
}: RelationshipInsightsProps) {
  if (!items.length) return null
  const HeaderIcon = icon === 'alert' ? AlertTriangle : Lightbulb
  const actionsById = new Map(actions.map((action) => [action.id, action]))
  return (
    <section aria-label={title} className="rounded-xl border border-navy/10 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <HeaderIcon className="h-4 w-4 text-teal" aria-hidden />
        <h3 className="text-sm font-semibold text-navy">{title}</h3>
      </div>
      <ul className="space-y-2.5">
        {items.map((item) => {
          const style = SEVERITY_STYLE[item.severity]
          const Icon = style.icon
          const action = item.action_id ? actionsById.get(item.action_id) : null
          return (
            <li key={item.id} className={`rounded-lg border ${style.border} ${style.bg} p-3`}>
              <div className="flex items-start gap-2.5">
                <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${style.color}`} aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-navy">{item.title}</p>
                  <p className="mt-0.5 text-xs text-navy/70">{item.detail}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
                    {item.evidence && (
                      <span className="rounded bg-navy/5 px-1.5 py-0.5 font-medium text-navy/60">
                        {item.evidence}
                      </span>
                    )}
                    {item.impact && (
                      <span className="font-semibold text-navy/70">
                        {item.impact.label}:{' '}
                        {formatKpiValue(item.impact.value, item.impact.format, currency)}
                      </span>
                    )}
                  </div>
                  {action && action.kind !== 'none' && onAction && (
                    <button
                      type="button"
                      onClick={() => onAction(action)}
                      className="mt-2 text-xs font-semibold text-teal hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/60"
                    >
                      {action.label}
                    </button>
                  )}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
