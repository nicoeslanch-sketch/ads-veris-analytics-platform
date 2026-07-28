import { FileSearch } from 'lucide-react'
import { formatNumber } from '../lib/format'
import type { MetricsResult } from '../lib/types'

interface Props {
  trace: NonNullable<MetricsResult['trazabilidad_ventas']>
}

export default function SalesTraceability({ trace }: Props) {
  const excluded = Object.entries(trace.lineas_excluidas)
    .filter(([key, value]) => key !== 'total' && value > 0)
    .map(([key, value]) => `${key.replace(/_/g, ' ')}: ${formatNumber(value)}`)
  const filters = [trace.filtros.desde, trace.filtros.hasta].filter(Boolean)

  return (
    <details className="mb-4 rounded-xl border border-teal/20 bg-white px-4 py-3 shadow-sm">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-navy">
        <FileSearch className="h-4 w-4 text-teal" />
        Trazabilidad de Ventas netas
        <span className="ml-auto text-xs font-normal text-navy/50">
          {trace.hoja ?? 'Hoja activa'} · {trace.columna ?? 'columna sin identificar'}
        </span>
      </summary>
      <div className="mt-3 grid gap-3 text-xs text-navy/65 sm:grid-cols-2 xl:grid-cols-4">
        <div>
          <p className="font-semibold text-navy">Origen y cálculo</p>
          <p>{trace.hoja ?? 'Hoja activa'}[{trace.columna ?? '—'}]</p>
          <p>{trace.formula_validacion ?? 'Suma de la columna de ventas validada'}</p>
        </div>
        <div>
          <p className="font-semibold text-navy">Cobertura</p>
          <p>{formatNumber(trace.lineas_incluidas)} líneas incluidas</p>
          <p>{formatNumber(trace.lineas_excluidas.total ?? 0)} excluidas</p>
          <p>{formatNumber(trace.cobertura_numerica_pct)}% con monto numérico</p>
        </div>
        <div>
          <p className="font-semibold text-navy">Fechas y filtros</p>
          <p>{formatNumber(trace.fechas_validas)} válidas · {formatNumber(trace.fechas_invalidas)} inválidas</p>
          <p>{filters.length ? filters.join(' → ') : 'Todo el periodo'}</p>
        </div>
        <div>
          <p className="font-semibold text-navy">Relaciones y exclusiones</p>
          <p>{trace.relaciones_utilizadas.length ? `${trace.relaciones_utilizadas.length} relación(es) validada(s)` : 'Sin relaciones'}</p>
          <p>{excluded.length ? excluded.join(' · ') : 'Sin exclusiones adicionales'}</p>
        </div>
      </div>
    </details>
  )
}
