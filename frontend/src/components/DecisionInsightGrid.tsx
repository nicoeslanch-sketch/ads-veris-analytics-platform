import { AlertTriangle, CheckCircle2, Lightbulb, TrendingUp } from 'lucide-react'

export interface DecisionInsight {
  title: string
  evidence: string
  action: string
  tone: 'teal' | 'gold' | 'coral' | 'green'
}

const TONES = {
  teal: {
    panel: 'border-teal/25 bg-teal/[0.055]',
    icon: 'bg-teal/10 text-teal',
    Icon: Lightbulb,
  },
  gold: {
    panel: 'border-gold/35 bg-gold/[0.07]',
    icon: 'bg-gold/15 text-gold',
    Icon: TrendingUp,
  },
  coral: {
    panel: 'border-coral/30 bg-coral/[0.06]',
    icon: 'bg-coral/10 text-coral',
    Icon: AlertTriangle,
  },
  green: {
    panel: 'border-green/25 bg-green/[0.055]',
    icon: 'bg-green/10 text-green',
    Icon: CheckCircle2,
  },
} as const

export default function DecisionInsightGrid({
  title = 'Lectura para decidir',
  items,
}: {
  title?: string
  items: DecisionInsight[]
}) {
  if (!items.length) return null
  return (
    <section>
      <h3 className="text-sm font-semibold text-navy">{title}</h3>
      <div className="mt-3 grid items-start gap-3 md:grid-cols-2">
        {items.map((item) => {
          const meta = TONES[item.tone]
          const Icon = meta.Icon
          return (
            <article key={`${item.title}-${item.evidence}`} className={`rounded-lg border p-4 ${meta.panel}`}>
              <div className="flex items-start gap-3">
                <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${meta.icon}`}>
                  <Icon className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <h4 className="text-sm font-semibold text-navy">{item.title}</h4>
                  <p className="mt-1 text-xs leading-relaxed text-navy/65">{item.evidence}</p>
                  <p className="mt-2 text-xs leading-relaxed text-navy/85">
                    <strong>Decisión sugerida:</strong> {item.action}
                  </p>
                </div>
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
