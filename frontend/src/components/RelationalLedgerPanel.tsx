import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, CalendarDays, GitMerge } from 'lucide-react'
import { ALL_PERIOD, monthPeriod, useDataset } from '../data/DatasetContext'
import { formatNumber } from '../lib/format'
import { periodSelectValue } from '../lib/periodPresentation'
import { AXIS_INK, CHART, GRID_STROKE, truncateLabel } from '../lib/charts'
import type { RelationalLedger } from '../lib/types'
import KpiValue from './ui/KpiValue'

type Measure = 'ventas' | 'utilidad' | 'unidades'
const labels = { ventas: 'Ventas netas', utilidad: 'Utilidad bruta', unidades: 'Unidades netas' }
const tipStyle = { maxWidth: 280, whiteSpace: 'normal' as const, overflowWrap: 'anywhere' as const, fontSize: 12 }

export default function RelationalLedgerPanel({ ledger, variant = 'summary' }: {
  ledger: RelationalLedger; variant?: 'summary' | 'explore'
}) {
  const [view, setView] = useState<'comercial' | 'resultado' | 'inventario'>(variant === 'explore' ? 'resultado' : 'comercial')
  const [measure, setMeasure] = useState<Measure>('ventas')
  const { period, setPeriod } = useDataset()
  const k = ledger.kpis ?? {}
  const money = (value: number | null | undefined) => value == null ? 'No disponible' : new Intl.NumberFormat('es-CL', {
    maximumFractionDigits: ledger.moneda === 'CLP' ? 0 : 2,
  }).format(value) + ' ' + ledger.moneda
  const axis = (value: number) => new Intl.NumberFormat('es-CL', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
  const months = ledger.periodo?.meses ?? []
  const years = [...new Set(months.map(m => m.slice(0, 4)))].sort().reverse()
  const selectedPeriod = periodSelectValue(period)
  const cards = [
    ['Ventas netas', k.ventas_netas], ['Utilidad bruta', k.utilidad_bruta],
    ['Resultado antes de impuestos', k.resultado_antes_impuestos], ['Cuentas por cobrar al corte', k.cuentas_por_cobrar],
  ] as const
  const resultRows = [
    { nombre: 'Ventas netas', valor: k.ventas_netas },
    { nombre: 'Costo de ventas', valor: k.costo_ventas_neto == null ? null : -k.costo_ventas_neto },
    { nombre: 'Gastos operacionales', valor: k.gastos_operacionales_netos == null ? null : -k.gastos_operacionales_netos },
    { nombre: 'Nóminas', valor: k.nominas == null ? null : -k.nominas },
    { nombre: 'Comisiones de cobro', valor: k.comisiones_cobro == null ? null : -k.comisiones_cobro },
    { nombre: 'Intereses pagados', valor: k.intereses_pagados == null ? null : -k.intereses_pagados },
    { nombre: 'Resultado antes de impuestos', valor: k.resultado_antes_impuestos },
  ]
  const ranking = [...(ledger.productos ?? [])].sort((a, b) => b[measure] - a[measure]).slice(0, 10)
  const rank = (rows: object[], key: string, unit: 'money' | 'count' = 'money', height = Math.max(160, Math.min(420, rows.length * 30 + 60))) => (
    <div style={{ height }} className="min-w-0" data-testid="ledger-ranking">
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <BarChart data={rows} layout="vertical" margin={{ top: 10, right: 16, bottom: 4, left: 0 }} accessibilityLayer>
          <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
          <XAxis type="number" tickFormatter={axis} tick={{ fontSize: 10, fill: AXIS_INK }} domain={[(v: number) => Math.min(0, v), (v: number) => Math.max(0, v)]} />
          <YAxis type="category" dataKey="nombre" width={118} tick={{ fontSize: 11, fill: AXIS_INK }} interval={0} tickFormatter={(v: string) => truncateLabel(v, 18)} />
          <ReferenceLine x={0} stroke={AXIS_INK} />
          <Tooltip contentStyle={tipStyle} formatter={(value) => [unit === 'money' ? money(Number(value)) : formatNumber(Number(value)), key === 'valor' ? 'Importe' : labels[key as Measure] ?? 'Valor']} />
          <Bar dataKey={key} fill={CHART.ingresos} maxBarSize={22} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
  if (!ledger.available) return <section className="border-y border-coral/30 py-4" role="status">
    <h2 className="flex items-center gap-2 text-base font-semibold"><AlertTriangle className="h-5 w-5 text-coral" />Conciliación pendiente</h2>
    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{ledger.advertencias.map((s, i) => <li key={i}>{s}</li>)}</ul>
  </section>
  return <div className="min-w-0 space-y-6" data-testid="relational-ledger">
    <div className="flex flex-wrap items-end justify-between gap-3 border-b border-navy/10 pb-3">
      <div><h2 className="text-base font-semibold text-navy">{variant === 'explore' ? 'Decisiones del período' : 'Negocio conciliado'}</h2>
        <p className="mt-1 text-xs text-navy/60">{ledger.periodo?.desde} a {ledger.periodo?.hasta} · {ledger.moneda}</p></div>
      <label className="min-w-0 text-xs font-medium text-navy"><CalendarDays className="mr-1 inline h-4 w-4" />Período
        <select aria-label="Período del negocio" value={selectedPeriod} onChange={e => {
          const v = e.target.value
          if (v === 'custom') return
          setPeriod(v === 'all' ? ALL_PERIOD : v.length === 4 ? { from: v + '-01-01', to: v + '-12-31', label: v } : monthPeriod(v))
        }} className="ml-2 max-w-full rounded-md border border-navy/20 bg-white p-2 text-sm">
          <option value="all">Todos los años</option>
          {selectedPeriod === 'custom' && <option value="custom">{period.label}</option>}
          <optgroup label="Años">{years.map(y => <option key={y} value={y}>{y}</option>)}</optgroup>
          <optgroup label="Meses">{[...months].reverse().map(m => <option key={m} value={m}>{m}</option>)}</optgroup>
        </select>
      </label>
    </div>
    <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map(([label, value]) => <div key={label} className="min-w-0 rounded-lg border border-navy/10 bg-white p-4">
        <p className="min-h-8 text-xs text-navy/65">{label}</p><KpiValue value={money(value)} maxPx={24} />
      </div>)}
    </div>
    <div role="group" aria-label="Análisis conciliado" className="flex flex-wrap gap-4 border-b border-navy/10">
      {([['comercial', 'Ventas y rentabilidad'], ['resultado', 'Resultado y caja'], ['inventario', 'Inventario']] as const).map(([id, label]) =>
        <button key={id} aria-pressed={view === id} onClick={() => setView(id)} className={'min-w-0 border-b-2 px-1 py-2 text-sm ' + (view === id ? 'border-teal font-semibold text-teal' : 'border-transparent text-navy/65')}>{label}</button>)}
    </div>
    {view === 'comercial' && <>
      <section className="min-w-0"><h3 className="text-sm font-semibold">Ventas, costos y utilidad por mes</h3>
        <div className="mt-3 h-72 min-w-0" data-testid="ledger-monthly"><ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <ComposedChart data={ledger.mensual} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} accessibilityLayer>
            <CartesianGrid stroke={GRID_STROKE} vertical={false} /><XAxis dataKey="mes" tick={{ fontSize: 10 }} minTickGap={28} />
            <YAxis tickFormatter={axis} width={55} tick={{ fontSize: 11 }} /><ReferenceLine y={0} stroke={AXIS_INK} />
            <Tooltip contentStyle={tipStyle} formatter={value => money(Number(value))} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="ventas" name="Ventas netas" fill={CHART.ingresos} maxBarSize={20} isAnimationActive={false} />
            <Line dataKey="costo" name="Costo de ventas" stroke="#b45309" type="linear" dot={false} strokeWidth={2} isAnimationActive={false} />
            <Line dataKey="utilidad" name="Utilidad bruta" stroke="#be185d" type="linear" dot={false} strokeWidth={2} isAnimationActive={false} />
          </ComposedChart></ResponsiveContainer></div>
      </section>
      <div className="grid min-w-0 gap-6 xl:grid-cols-2">
        <section className="min-w-0"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold">Productos · Top 10</h3>
          <select aria-label="Medida de productos" value={measure} onChange={e => setMeasure(e.target.value as Measure)} className="max-w-full rounded-md border border-navy/20 bg-white p-2 text-xs">{Object.entries(labels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></div>
          {rank(ranking, measure, measure === 'unidades' ? 'count' : 'money')}
          {variant === 'explore' && ranking[0] && <p className="text-xs leading-relaxed text-navy/70">{ranking[0].nombre} lidera en {labels[measure].toLowerCase()}. Compara su margen y disponibilidad antes de aumentar las compras.</p>}
        </section>
        <section className="min-w-0"><h3 className="text-sm font-semibold">Utilidad bruta por sucursal</h3>{rank(ledger.sucursales ?? [], 'utilidad')}
          <p className="text-xs text-navy/60">Detalle de venta → lote → sucursal. Las devoluciones se descuentan por su fecha.</p></section>
      </div>
    </>}
    {view === 'resultado' && <div className="grid min-w-0 gap-6 xl:grid-cols-2">
      <section className="min-w-0"><h3 className="text-sm font-semibold">Composición del resultado · {ledger.moneda}</h3>{rank(resultRows, 'valor')}
        {variant === 'explore' && k.resultado_antes_impuestos != null && k.resultado_antes_impuestos < 0 && <p className="text-xs text-navy/70">La utilidad bruta no alcanza a cubrir los gastos, nóminas, comisiones e intereses registrados. Revisa estos rubros antes de concluir que vender más resolverá la pérdida.</p>}</section>
      <section className="min-w-0"><h3 className="text-sm font-semibold">Caja y obligaciones</h3><dl className="mt-3 divide-y divide-navy/10">{[
        ['Depósitos netos del período', k.depositos_netos], ['Flujo antes de liquidación de IVA', k.flujo_caja_antes_iva],
        ['CxC acumuladas al corte', k.cuentas_por_cobrar], ['CxP acumuladas al corte', k.cuentas_por_pagar],
        ['IVA débito neto del período', k.iva_debito_neto], ['IVA crédito del período', k.iva_credito],
      ].map(([label, value]) => <div key={String(label)} className="grid min-w-0 grid-cols-2 gap-3 py-3"><dt className="text-xs text-navy/65">{label}</dt><dd className="min-w-0 text-right"><KpiValue value={money(value as number | null)} maxPx={17} /></dd></div>)}</dl>
        <p className="mt-3 text-xs text-navy/60">El flujo no es el saldo del banco. Los saldos incluyen movimientos anteriores al período seleccionado; el IVA no constituye una declaración tributaria.</p></section>
    </div>}
    {view === 'inventario' && <section className="min-w-0"><h3 className="text-sm font-semibold">Inventario al corte</h3>
      <p className="mt-2 text-sm">{formatNumber(k.stock_unidades ?? 0)} unidades · {money(k.inventario_valorizado)}</p>
      {(ledger.inventario_lento?.length ?? 0) > 0 ? <><h4 className="mt-5 text-sm font-semibold">Stock con 90 días sin venta observada</h4>{rank(ledger.inventario_lento ?? [], 'valor')}
        <p className="text-xs text-navy/70">Revisa estacionalidad, stock disponible durante el período, precio y marketing. La ausencia de ventas no demuestra por sí sola que debas retirar el producto.</p></> : <p className="mt-4 text-sm text-navy/65">No hay productos con stock que cumplan el umbral de 90 días sin venta en este corte.</p>}
    </section>}
    <details className="border-y border-navy/10 py-3"><summary className="cursor-pointer text-sm font-semibold"><GitMerge className="mr-2 inline h-4 w-4" />Fuentes, conexiones y criterios</summary>
      <ul className="mt-3 list-disc space-y-2 pl-5 text-xs text-navy/65">{ledger.criterios?.map(s => <li key={s}>{s}</li>)}</ul>
      <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr><th className="p-2">Desde</th><th>Hacia</th><th>Clave</th><th>Sin vínculo</th></tr></thead><tbody>{ledger.relaciones.map((r, i) => <tr key={i} className="border-t border-navy/10"><td className="p-2">{r.desde}</td><td>{r.hasta}</td><td>{r.clave}</td><td>{r.sin_correspondencia}</td></tr>)}</tbody></table></div>
    </details>
  </div>
}
