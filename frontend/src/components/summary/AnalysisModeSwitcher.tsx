import { Layers3, Link2, Rows3, TrendingUp, type LucideIcon } from 'lucide-react'
import { ANALYSIS_MODES, type AnalysisMode } from '../../lib/analysisModes'

type Mode = AnalysisMode

/** Ícono por modo. Los textos y el mapeo viven en `analysisModes` (puro). */
const MODE_ICON: Record<Mode, LucideIcon> = {
  single: Layers3,
  append_join: TrendingUp,
  append: Rows3,
  join: Link2,
}

interface AnalysisModeSwitcherProps {
  mode: Mode
  onSelect: (mode: Mode) => void
  /** Mapa modo → motivo de deshabilitación (tooltip). */
  disabledModes?: Partial<Record<Mode, string>>
  busy?: boolean
}

/** Selector segmentado, compacto y accesible. Solo presentación: el estado y
 * los handlers viven en `ActiveSheetSelector`. Una línea en escritorio, rejilla
 * 2×2 en pantallas chicas. */
export default function AnalysisModeSwitcher({
  mode,
  onSelect,
  disabledModes = {},
  busy = false,
}: AnalysisModeSwitcherProps) {
  return (
    <div
      role="group"
      aria-label="Modo de análisis"
      className="grid grid-cols-2 gap-1 rounded-xl border border-navy/15 bg-white p-1 sm:inline-grid sm:auto-cols-max sm:grid-flow-col"
    >
      {ANALYSIS_MODES.map(({ mode: value, label }) => {
        const Icon = MODE_ICON[value]
        const active = mode === value
        const disabledReason = disabledModes[value]
        const disabled = busy || Boolean(disabledReason)
        return (
          <button
            key={value}
            type="button"
            aria-pressed={active}
            aria-label={label}
            disabled={disabled}
            title={disabledReason || undefined}
            onClick={() => onSelect(value)}
            className={[
              'inline-flex min-h-11 min-w-0 items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-xs font-semibold transition-colors sm:min-h-0 sm:px-3',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/60 focus-visible:ring-offset-1',
              'disabled:cursor-not-allowed disabled:opacity-45',
              active
                ? 'border border-teal bg-teal/10 text-navy shadow-sm'
                : 'border border-transparent text-navy/60 hover:bg-navy/5',
            ].join(' ')}
          >
            <Icon className={`h-3.5 w-3.5 shrink-0 ${active ? 'text-teal' : ''}`} aria-hidden />
            <span className="text-center leading-tight sm:whitespace-nowrap">{label}</span>
            {active && (
              <span className="ml-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal" aria-hidden />
            )}
          </button>
        )
      })}
    </div>
  )
}
