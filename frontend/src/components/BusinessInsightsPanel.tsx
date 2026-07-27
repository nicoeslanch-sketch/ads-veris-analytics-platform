import {
  AlertTriangle,
  Lightbulb,
  ShieldAlert,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react'
import Card from './ui/Card'
import type { BusinessInsight, InsightTone } from '../lib/businessInsights'

const TONE: Record<InsightTone, { icon: LucideIcon; label: string; chip: string; edge: string }> = {
  riesgo: {
    icon: ShieldAlert,
    label: 'Riesgo',
    chip: 'bg-coral/10 text-coral',
    edge: 'border-l-coral',
  },
  atencion: {
    icon: AlertTriangle,
    label: 'Atención',
    chip: 'bg-gold/15 text-amber-700',
    edge: 'border-l-gold',
  },
  oportunidad: {
    icon: Lightbulb,
    label: 'Oportunidad',
    chip: 'bg-teal/10 text-teal',
    edge: 'border-l-teal',
  },
  positivo: {
    icon: TrendingUp,
    label: 'A favor',
    chip: 'bg-green/10 text-green',
    edge: 'border-l-green',
  },
}

/** Lo que diferencia Explorar de Resumen: aquí no se repiten los gráficos, se
 * interpreta lo que los números significan para el negocio y qué conviene
 * hacer. Cada lectura declara su evidencia para poder contrastarla. */
export default function BusinessInsightsPanel({ insights }: { insights: BusinessInsight[] }) {
  if (insights.length === 0) return null
  return (
    <Card>
      <div className="flex items-center gap-2">
        <Lightbulb className="h-4.5 w-4.5 text-gold" />
        <h2 className="text-base font-semibold text-navy">Qué dicen tus números</h2>
      </div>
      <p className="mt-1 text-xs text-navy/55">
        Lectura de los mismos datos del resumen, pero explicando qué significan y qué conviene
        revisar. Cada punto muestra la cifra en que se basa.
      </p>
      <ul className="mt-4 grid gap-3 xl:grid-cols-2">
        {insights.map((insight) => {
          const tone = TONE[insight.tone]
          const Icon = tone.icon
          return (
            <li
              key={insight.id}
              className={`rounded-lg border border-navy/10 border-l-4 bg-white p-4 ${tone.edge}`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Icon className="h-4 w-4 shrink-0 text-navy/45" />
                <h3 className="min-w-0 flex-1 text-sm font-semibold text-navy">{insight.titulo}</h3>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${tone.chip}`}>
                  {tone.label}
                </span>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-navy/70">{insight.significado}</p>
              <p className="mt-2 text-xs leading-relaxed text-navy/80">
                <span className="font-semibold">Qué hacer:</span> {insight.accion}
              </p>
              <p className="mt-2 rounded-md bg-navy/[0.04] px-2.5 py-1.5 text-[11px] leading-relaxed text-navy/55">
                {insight.evidencia}
              </p>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
