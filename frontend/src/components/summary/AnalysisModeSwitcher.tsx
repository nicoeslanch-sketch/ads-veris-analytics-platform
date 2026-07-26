import { Layers3, Link2, Rows3, Settings2, TrendingUp, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ANALYSIS_MODES, type AnalysisMode } from '../../lib/analysisModes'

type Mode = AnalysisMode

/** Ícono por modo. Los textos y el mapeo viven en `analysisModes` (puro). */
const MODE_ICON: Record<Mode, LucideIcon> = {
  single: Layers3,
  append_join: TrendingUp,
  append: Rows3,
  join: Link2,
}

const MODE_TONE: Record<Mode, string> = {
  single: 'border-teal/20 bg-teal/10 text-teal hover:bg-teal/15',
  append_join: 'border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100',
  append: 'border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100',
  join: 'border-orange-200 bg-orange-50 text-orange-700 hover:bg-orange-100',
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
      className="flex min-w-max items-stretch gap-2"
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
              'group relative inline-flex min-h-12 min-w-[9.5rem] items-center justify-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold shadow-sm transition-all duration-200',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/60 focus-visible:ring-offset-1',
              'disabled:cursor-not-allowed disabled:opacity-45',
              active
                ? 'border-transparent bg-gradient-to-r from-teal to-sky-600 text-white shadow-md shadow-teal/20 hover:-translate-y-0.5 hover:shadow-lg'
                : MODE_TONE[value],
            ].join(' ')}
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden />
            <span className="text-center leading-tight whitespace-nowrap">{label}</span>
            {active && (
              <span
                className="absolute right-2 top-2 h-2 w-2 rounded-full border-2 border-white bg-white/60"
                aria-hidden
              />
            )}
          </button>
        )
      })}
      <Link
        to="/estandarizacion"
        className="inline-flex min-h-12 min-w-[9.5rem] items-center justify-center gap-2 rounded-xl border border-orange-200 bg-orange-50 px-3 py-2 text-xs font-semibold text-orange-700 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-orange-100 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-300 focus-visible:ring-offset-1"
      >
        <Settings2 className="h-4 w-4 shrink-0" aria-hidden />
        <span className="whitespace-nowrap">Administrar hojas</span>
      </Link>
    </div>
  )
}
