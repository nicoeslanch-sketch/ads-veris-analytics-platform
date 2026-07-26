import { useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Link2, ShieldCheck } from 'lucide-react'
import type { RelationshipAction, RelationshipDashboard, RelationshipTableColumn } from '../../lib/types'
import { formatKpiValue, templateDescription, templateLabel } from '../../lib/relationshipDashboard'
import RelationshipKpis from './RelationshipKpis'
import RelationshipCharts from './RelationshipCharts'
import RelationshipInsights from './RelationshipInsights'

interface RelationshipDashboardViewProps {
  dashboard: RelationshipDashboard
}

function TableCell({ value, format, currency }: { value: string | number | null; format: RelationshipTableColumn['format']; currency: string }) {
  if (value === null || value === undefined) {
    return <span className="text-navy/35">—</span>
  }
  if (typeof value === 'number') return <>{formatKpiValue(value, format, currency)}</>
  return <>{value}</>
}

const STATE_BADGE: Record<string, string> = {
  critico: 'bg-coral/15 text-coral',
  alto: 'bg-coral/10 text-coral',
  medio: 'bg-gold/15 text-navy',
  sano: 'bg-green/15 text-green',
  sin_datos: 'bg-navy/10 text-navy/50',
}

export default function RelationshipDashboardView({ dashboard }: RelationshipDashboardViewProps) {
  const { relation, currency, quality } = dashboard
  const [highlightTable, setHighlightTable] = useState<string | null>(null)
  const tableRef = useRef<HTMLDivElement | null>(null)

  const handleAction = (action: RelationshipAction) => {
    if ((action.kind === 'highlight' || action.kind === 'filter_table') && action.target) {
      setHighlightTable(action.target)
      tableRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }

  const coverageTone = quality.coverage_pct >= 95
    ? 'text-green'
    : quality.coverage_pct >= 80
      ? 'text-navy'
      : 'text-coral'

  const actionable = dashboard.actions.filter((action) => action.kind !== 'none')

  return (
    <div className="@container space-y-3">
      {/* Encabezado compacto de la relación */}
      <div className="rounded-lg border border-navy/10 bg-white p-3.5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Link2 className="h-4 w-4 text-teal" aria-hidden />
              <span className="rounded-full bg-teal/10 px-2 py-0.5 text-[11px] font-semibold text-teal">
                {templateLabel(relation.template)}
              </span>
            </div>
            <h2 className="mt-1.5 text-lg font-bold text-navy">{relation.label}</h2>
            <p className="mt-0.5 text-xs text-navy/60">{templateDescription(relation.template)}</p>
            <p className="mt-1 text-[11px] text-navy/50">
              Clave: {relation.left_keys.join(' + ')} ↔ {relation.right_keys.join(' + ')}
            </p>
            <p className="mt-0.5 text-[11px] text-navy/45">
              {relation.append_sheets?.length
                ? `${relation.append_sheets.join(', ')} apiladas antes de relacionar con ${relation.right_sheet}`
                : `${relation.left_sheet} relacionada con ${relation.right_sheet}`}
              {' · '}{(relation.cardinality ?? 'relación validada').replace(/_/g, ' ')}
            </p>
          </div>
          <div className={`flex items-center gap-2 rounded-lg border px-3 py-2 ${
            dashboard.available
              ? 'border-green/30 bg-green/[0.07]'
              : 'border-coral/30 bg-coral/[0.07]'
          }`}>
            {dashboard.available
              ? <ShieldCheck className="h-4 w-4 text-green" aria-hidden />
              : <AlertTriangle className="h-4 w-4 text-coral" aria-hidden />}
            <div>
              <p className="text-[11px] font-semibold text-navy">
                {dashboard.available ? 'Conexión segura' : 'Conexión no disponible'}
              </p>
              <p className={`text-[11px] font-medium ${coverageTone}`}>
                {formatKpiValue(quality.coverage_pct, 'percent', currency)} de correspondencia
              </p>
            </div>
          </div>
        </div>
        {quality.warnings.length > 0 && (
          <div className="mt-3 flex items-start gap-2 rounded-lg bg-gold/10 px-3 py-2 text-[11px] text-navy/70">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gold" aria-hidden />
            <div>
              {quality.warnings.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </div>
          </div>
        )}
      </div>

      {!dashboard.available ? (
        <div className="rounded-xl border border-navy/10 bg-white p-6 text-center text-sm text-navy/60 shadow-sm">
          {dashboard.message ?? 'Esta relación no tiene variables suficientes para un dashboard.'}
        </div>
      ) : (
        <>
          <RelationshipKpis kpis={dashboard.kpis} currency={currency} />
          <div className="grid min-w-0 gap-3 @min-[720px]:grid-cols-[minmax(0,1fr)_280px]">
            <div className="min-w-0 space-y-3">
              <RelationshipCharts charts={dashboard.charts} currency={currency} />

              {dashboard.table && dashboard.table.rows.length > 0 && (
                <div
                  ref={tableRef}
                  className={`rounded-lg border bg-white p-3.5 shadow-sm transition-shadow ${
                    highlightTable === dashboard.table.id ? 'border-teal ring-2 ring-teal/40' : 'border-navy/10'
                  }`}
                >
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold text-navy">{dashboard.table.title}</h3>
                    <span className="text-[11px] text-navy/50">
                      {dashboard.table.matched_rows != null ? (
                        <>
                          {dashboard.table.rows.length} visibles ·{' '}
                          {dashboard.table.matched_rows} con costo
                          {dashboard.table.unmatched_rows
                            ? ` · ${dashboard.table.unmatched_rows} sin correspondencia`
                            : ''}
                        </>
                      ) : (
                        <>{dashboard.table.rows.length} de {dashboard.table.total_rows}</>
                      )}
                    </span>
                  </div>
                  <div className="max-h-[28rem] overflow-auto">
                    <table className="w-full min-w-[32rem] text-left text-xs">
                      <thead className="sticky top-0 z-10 bg-white">
                        <tr className="border-b border-navy/10 text-navy/55">
                          <th className="w-8 px-2 py-2 font-semibold">#</th>
                          {dashboard.table.columns.map((column) => (
                            <th key={column.key} className="whitespace-nowrap px-2 py-2 font-semibold">
                              {column.label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {dashboard.table.rows.map((row, index) => (
                          <tr key={index} className="border-b border-navy/5 last:border-0">
                            <td className="px-2 py-2 text-navy/35">{index + 1}</td>
                            {dashboard.table!.columns.map((column) => {
                              const raw = row[column.key]
                              const isState = column.key === 'estado' && typeof raw === 'string'
                              return (
                                <td key={column.key} className="whitespace-nowrap px-2 py-2 text-navy/80">
                                  {isState ? (
                                    <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${STATE_BADGE[raw as string] ?? 'bg-navy/10 text-navy/60'}`}>
                                      {raw}
                                    </span>
                                  ) : (
                                    <TableCell value={raw} format={column.format} currency={currency} />
                                  )}
                                </td>
                              )
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
            <aside className="space-y-3" aria-label="Hallazgos y acciones">
              <RelationshipInsights
                title="Hallazgos clave"
                icon="lightbulb"
                items={dashboard.findings}
                actions={dashboard.actions}
                currency={currency}
                onAction={handleAction}
              />
              <RelationshipInsights
                title="Alertas"
                icon="alert"
                items={dashboard.alerts}
                actions={dashboard.actions}
                currency={currency}
                onAction={handleAction}
              />
              {actionable.length > 0 && (
                <section className="rounded-lg border border-navy/10 bg-white p-3.5 shadow-sm">
                  <div className="mb-2 flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green" aria-hidden />
                    <h3 className="text-sm font-semibold text-navy">Acciones recomendadas</h3>
                  </div>
                  <div className="space-y-1.5">
                    {actionable.map((action) => (
                      <button
                        key={action.id}
                        type="button"
                        onClick={() => handleAction(action)}
                        className="flex w-full items-center gap-2 rounded-md border border-navy/10 px-2.5 py-2 text-left text-[11px] font-semibold text-navy transition-colors hover:border-teal/40 hover:bg-teal/[0.04]"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-green" aria-hidden />
                        {action.label}
                      </button>
                    ))}
                  </div>
                </section>
              )}
            </aside>
          </div>
        </>
      )}
    </div>
  )
}
