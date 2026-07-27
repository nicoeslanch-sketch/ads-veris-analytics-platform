import { SlidersHorizontal, X } from 'lucide-react'
import type {
  BusinessFilterKey,
  BusinessFilters,
} from '../lib/types'

const FILTERS: Array<{ key: BusinessFilterKey; label: string }> = [
  { key: 'sucursal', label: 'Sucursal' },
  { key: 'canal', label: 'Canal' },
  { key: 'vendedor', label: 'Vendedor' },
  { key: 'categoria', label: 'Categoría' },
  { key: 'producto', label: 'Producto' },
  { key: 'moneda', label: 'Moneda' },
  { key: 'periodo_cotizado', label: 'Periodo cotizado' },
  { key: 'equipo', label: 'Equipo / grupo' },
  { key: 'subgrupo', label: 'Subgrupo' },
  { key: 'agencia_pago', label: 'Agencia de pago' },
  { key: 'forma_pago', label: 'Forma de pago' },
]

interface BusinessFilterBarProps {
  options: Partial<Record<BusinessFilterKey, string[]>>
  value: BusinessFilters
  disabled?: boolean
  onChange: (filters: BusinessFilters) => void
}

export default function BusinessFilterBar({
  options,
  value,
  disabled = false,
  onChange,
}: BusinessFilterBarProps) {
  const available = FILTERS.filter(({ key }) => (options[key]?.length ?? 0) > 1)
  const activeCount = Object.values(value).filter(Boolean).length

  if (available.length === 0) return null

  return (
    <section
      aria-label="Filtros del dashboard"
      className="mb-6 rounded-2xl border border-navy/10 bg-white p-4 shadow-[0_10px_30px_rgba(15,53,75,0.07)]"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-teal/10">
            <SlidersHorizontal className="h-4 w-4 text-teal" />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-navy">Filtros del negocio</h2>
            <p className="text-[11px] text-navy/50">
              Todos los KPI y gráficos usan la misma selección.
            </p>
          </div>
        </div>
        {activeCount > 0 && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onChange({})}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-teal transition-colors hover:bg-teal/10 disabled:cursor-wait disabled:opacity-45"
          >
            <X className="h-3.5 w-3.5" />
            Limpiar {activeCount} filtro{activeCount === 1 ? '' : 's'}
          </button>
        )}
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {available.map(({ key, label }) => (
          <label key={key} className="min-w-0 text-[11px] font-semibold text-navy/55">
            {label}
            <select
              value={value[key] ?? ''}
              disabled={disabled}
              onChange={(event) => {
                const selected = event.target.value
                const next = { ...value }
                if (selected) next[key] = selected
                else delete next[key]
                onChange(next)
              }}
              className="mt-1.5 w-full truncate rounded-lg border border-navy/15 bg-white px-2.5 py-2 text-xs font-medium text-navy outline-none transition-colors hover:border-teal/45 focus:border-teal focus:ring-2 focus:ring-teal/10 disabled:cursor-wait disabled:bg-navy/[0.03] disabled:text-navy/40"
            >
              <option value="">Todos</option>
              {options[key]?.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
        ))}
      </div>

      {activeCount > 0 && (
        <p className="mt-3 text-[11px] leading-relaxed text-navy/50">
          La selección se aplica antes de recalcular KPI, porcentajes y gráficos.
          Un indicador queda no disponible si su fuente no contiene la dimensión
          elegida; ADS Veris no prorratea ni inventa resultados.
        </p>
      )}
    </section>
  )
}
