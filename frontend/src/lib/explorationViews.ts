import type { MetricsResult, ProductPatterns, RelationalLedger } from './types'
import type { ExplorationMeasure } from './explorationAnalysis'

export type ExplorationChartKind = 'line' | 'bars' | 'comparison' | 'pareto' | 'matrix' | 'scatter'
export interface ExplorationView {
  id: string
  label: string
  category: 'Evolución' | 'Composición' | 'Productos' | 'Operación'
  kind: ExplorationChartKind
  unit: 'money' | 'count' | 'percent'
  rows: Array<{ name: string; [key: string]: string | number | null }>
  keys: { key: string; label: string }[]
  evidence: string
  action: string
}
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const monthNames = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
const monthIndex = (month: string) => Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7))

// Eligibility belongs beside the transformation, not in the rendering layer.
export function buildExplorationViews({ metrics, ledger, measure, dimension, from, to }: {
  metrics?: MetricsResult; ledger?: RelationalLedger; measure?: ExplorationMeasure
  dimension?: string; from?: string | null; to?: string | null
}): ExplorationView[] {
  const views: ExplorationView[] = []
  const unit = measure?.format === 'porcentaje' ? 'percent' : measure?.format === 'numero' ? 'count' : 'money'
  const inside = (period: string) => (!from || period >= from.slice(0, 7)) && (!to || period <= to.slice(0, 7))
  const partialBoundary = (period: string) => Boolean(
    (from && period === from.slice(0, 7) && from.slice(8, 10) !== '01') ||
    (to && period === to.slice(0, 7) && Number(to.slice(8, 10)) !== new Date(Date.UTC(Number(to.slice(0, 4)), Number(to.slice(5, 7)), 0)).getUTCDate()))
  const series = (ledger?.mensual?.map(row => ({ period: row.mes, value: row.ventas, partial: partialBoundary(row.mes) })) ?? measure?.series ?? [])
    .filter(row => /^\d{4}-\d{2}$/.test(row.period) && inside(row.period)).sort((a, b) => a.period.localeCompare(b.period))
  const full = series.filter(row => !row.partial && !partialBoundary(row.period) && finite(row.value))
  if (ledger && series.length) views.push({ id: 'trend', label: 'Ventas, costo y utilidad', category: 'Evolución', kind: 'comparison', unit: 'money',
    rows: (ledger.mensual ?? []).filter(row => inside(row.mes)).map(row => ({ name: row.mes, ventas: row.ventas, costo: row.costo, utilidad: row.utilidad })),
    keys: [{ key: 'ventas', label: 'Ventas netas' }, { key: 'costo', label: 'Costo de ventas' }, { key: 'utilidad', label: 'Utilidad bruta' }],
    evidence: 'Importes conciliados por fecha de cada movimiento, incluidas devoluciones.', action: 'Si las ventas crecen sin una mejora de utilidad, revisa costos, descuentos y mezcla de productos.' })
  const years = [...new Set(full.map(row => row.period.slice(0, 4)))].slice(-5)
  const comparableMonths = monthNames.map((_, i) => String(i + 1).padStart(2, '0')).filter(month => years.filter(year => full.some(row => row.period === year + '-' + month)).length >= 2)
  if (comparableMonths.length) views.push({ id: 'year-comparison', label: 'Mismo mes entre años', category: 'Evolución', kind: 'comparison', unit,
    rows: comparableMonths.map(month => Object.fromEntries([['name', monthNames[Number(month) - 1]], ...years.map(year => [year, full.find(row => row.period === year + '-' + month)?.value ?? null])]) as ExplorationView['rows'][number]),
    keys: years.map(year => ({ key: year, label: year })), evidence: 'Solo meses comparables sin marca de parcialidad; un hueco no se convierte en cero.',
    action: 'Compara el mismo mes para reducir el efecto del calendario. Un cambio puede reflejar precios, volumen o cobertura del archivo.' })
  const deltas = full.flatMap((row, i) => i && monthIndex(row.period) - monthIndex(full[i - 1].period) === 1
    ? [{ name: row.period, value: row.value! - full[i - 1].value! }] : [])
  if (deltas.length) views.push({ id: 'monthly-change', label: 'Cambio entre meses consecutivos', category: 'Evolución', kind: 'bars', unit,
    rows: deltas.slice(-24), keys: [{ key: 'value', label: unit === 'percent' ? 'Cambio en puntos porcentuales' : 'Cambio absoluto' }],
    evidence: 'Diferencia frente al mes anterior completo, no una tasa de crecimiento.', action: 'Investiga los mayores cambios por producto o segmento antes de atribuir una causa.' })
  const selected = measure?.dimensions.find(row => row.name === dimension) ?? measure?.dimensions[0]
  const groups = ledger?.productos?.map(row => ({ name: row.nombre, value: row.ventas })) ?? selected?.groups ?? []
  const ranked = groups.filter(row => finite(row.value)).slice().sort((a, b) => b.value! - a.value!)
  if (ledger && ranked.length) views.push({ id: 'product-ranking', label: 'Productos por ventas netas', category: 'Productos', kind: 'bars', unit: 'money',
    rows: ranked.slice(0, 10).map(row => ({ name: row.name, value: row.value })), keys: [{ key: 'value', label: 'Ventas netas' }],
    evidence: 'Hasta diez productos con mayores ingresos netos, no necesariamente más unidades.', action: 'Revisa margen, stock y recurrencia antes de reforzar compras o promoción del líder.' })
  const total = ledger?.kpis?.ventas_netas ?? measure?.value
  const sum = ranked.reduce((n, row) => n + row.value!, 0)
  if ((ledger || measure?.id === 'ingresos') && ranked.length > 1 && ranked.every(row => row.value! >= 0) && finite(total) && total > 0 && Math.abs(sum - total) <= Math.max(.02, Math.abs(total) * .000001)) {
    const rows = ranked.slice(0, 9).map(row => ({ name: row.name, value: row.value! }))
    if (ranked.length > 9) rows.push({ name: `Otros (${ranked.length - 9})`, value: ranked.slice(9).reduce((n, row) => n + row.value!, 0) })
    let cumulative = 0
    views.push({ id: 'concentration', label: 'Concentración de ingresos', category: 'Composición', kind: 'pareto', unit: 'money',
      rows: rows.map(row => ({ ...row, cumulative: (cumulative += row.value) / total * 100 })), keys: [{ key: 'value', label: 'Ingresos' }],
      evidence: 'La distribución concilia con el total y no contiene grupos negativos. La línea muestra el porcentaje acumulado.',
      action: 'Evalúa la dependencia de pocos grupos; no confundas concentración de ingresos con rentabilidad.' })
  }
  if (measure?.movement?.values.length) {
    const movement = measure.movement.values.filter(row => inside(row.period) && finite(row.value))
    const names = [...new Set(movement.map(row => row.name))].slice(0, 9)
    const periods = [...new Set(movement.map(row => row.period))].sort().slice(-18)
    if (periods.length > 1 && names.length > 1) views.push({ id: 'segment-calendar', label: 'Mapa mensual por ' + measure.movement.dimension.toLowerCase(), category: 'Composición', kind: 'matrix', unit,
      rows: names.map(name => Object.fromEntries([['name', name], ...periods.map(period => [period, movement.find(row => row.name === name && row.period === period)?.value ?? null])]) as ExplorationView['rows'][number]),
      keys: periods.map(period => ({ key: period, label: period })), evidence: 'Hasta nueve grupos y dieciocho meses. Los espacios sin observación no se rellenan con cero.',
      action: 'Localiza en qué grupos y meses cambia la actividad; contrasta campañas y disponibilidad antes de explicar el cambio.' })
  }
  const productGroups = metrics?.analisis_negocio
    ? Object.entries(metrics.analisis_negocio.agrupaciones ?? {}).find(([name]) => /producto/i.test(name))?.[1] ?? []
    : metrics?.tipo_analisis === 'ventas' ? metrics.top_productos ?? [] : []
  const pairs = ledger?.productos?.map(row => ({ name: row.nombre, x: row.ventas, y: row.utilidad })) ?? productGroups.filter(row => row.cobertura_costos_pct === 100 && finite(row.utilidad)).map(row => ({ name: row.nombre, x: row.ingresos, y: row.utilidad! }))
  if (pairs.length > 1) views.push({ id: 'sales-profit', label: 'Ingresos frente a utilidad por producto', category: 'Productos', kind: 'scatter', unit: 'money',
    rows: pairs.slice(0, 100), keys: [{ key: 'x', label: 'Ingresos netos' }, { key: 'y', label: 'Utilidad bruta' }],
    evidence: 'Cada punto es un producto con costos pareados completos. Hasta cien productos del resultado publicado.',
    action: 'Los productos con ventas altas y utilidad baja requieren revisar costos y descuentos; compara también el margen antes de reinvertir.' })
  const activity = metrics?.analisis_negocio ? null : metrics?.actividad_productos
  if (activity?.productos.length) views.push({ id: 'inactivity', label: 'Meses sin venta positiva observada', category: 'Productos', kind: 'bars', unit: 'count',
    rows: activity.productos.map(row => ({ name: row.nombre + ' · ' + row.id, value: row.meses_sin_venta_observada })), keys: [{ key: 'value', label: 'Meses sin venta observada' }],
    evidence: `Corte ${activity.fecha_corte}; ${activity.total_sin_ventas} productos cumplen el criterio, hasta diez visibles.`,
    action: 'Comprueba stock, temporada y cobertura. Prueba precio o marketing antes de reducir reposición; ausencia de ventas no prueba falta de demanda.' })
  if (ledger?.inventario_lento?.length) views.push({ id: 'slow-stock', label: 'Capital en stock sin ventas recientes', category: 'Productos', kind: 'bars', unit: 'money',
    rows: ledger.inventario_lento.map(row => ({ name: row.nombre, value: row.valor })), keys: [{ key: 'value', label: 'Inventario valorizado' }],
    evidence: 'Productos con stock y 90 días sin venta observada, o sin venta previa conocida, al corte del balance.',
    action: 'Revisa temporada, antigüedad y margen antes de liquidar, rediseñar o reducir nuevas compras.' })
  if (!metrics?.analisis_negocio && metrics?.tipo_analisis === 'ventas' && metrics.por_dia_semana && metrics.por_dia_semana.length > 1) views.push({ id: 'weekday', label: 'Actividad por día de semana', category: 'Operación', kind: 'bars', unit: 'money',
    rows: metrics.por_dia_semana.map(row => ({ name: row.dia, value: row.ingresos })), keys: [{ key: 'value', label: 'Ingresos acumulados' }],
    evidence: 'Importes acumulados por día, no promedio por jornada abierta.', action: 'Contrasta días abiertos, feriados y dotación antes de cambiar horarios o personal.' })
  if (ledger?.kpis) {
    const k = ledger.kpis
    const result = [['Ventas netas', k.ventas_netas], ['Costo de ventas', k.costo_ventas_neto == null ? null : -k.costo_ventas_neto], ['Gastos operacionales', k.gastos_operacionales_netos == null ? null : -k.gastos_operacionales_netos], ['Nóminas', k.nominas == null ? null : -k.nominas], ['Comisiones', k.comisiones_cobro == null ? null : -k.comisiones_cobro], ['Intereses', k.intereses_pagados == null ? null : -k.intereses_pagados], ['Resultado antes de impuestos', k.resultado_antes_impuestos]] as const
    if (result.every(([, value]) => finite(value))) views.push({ id: 'result-drivers', label: 'Ingresos y deducciones del resultado', category: 'Operación', kind: 'bars', unit: 'money', rows: result.map(([name, value]) => ({ name, value: value! })), keys: [{ key: 'value', label: 'Importe' }], evidence: 'Rubros y resultado final conciliados; el resultado es un total, no otro rubro para sumar.', action: k.resultado_antes_impuestos! < 0 ? 'La utilidad no cubre las deducciones registradas. Revisa sus causas y recurrencia antes de asumir que vender más resolverá la pérdida.' : 'Contrasta el resultado con los cobros y pagos: utilidad no equivale a efectivo disponible.' })
    const balances = [['Cuentas por cobrar', k.cuentas_por_cobrar], ['Cuentas por pagar', k.cuentas_por_pagar], ['Inventario valorizado', k.inventario_valorizado]] as const
    if (balances.filter(([, value]) => finite(value)).length > 1) views.push({ id: 'working-capital', label: 'Saldos operativos al corte', category: 'Operación', kind: 'bars', unit: 'money', rows: balances.filter(([, value]) => finite(value)).map(([name, value]) => ({ name, value: value! })), keys: [{ key: 'value', label: 'Saldo observado' }], evidence: 'Saldos acumulados al corte, no flujos del período ni saldo bancario.', action: 'Revisa vencimientos de cobro y pago y stock inmovilizado antes de comprometer nuevas compras.' })
  }
  addProductViews(views, ledger?.patrones_productos ?? (metrics?.analisis_negocio ? null : metrics?.patrones_productos), inside, partialBoundary)
  return views
}

function addProductViews(views: ExplorationView[], patterns: ProductPatterns | null | undefined, inside: (month: string) => boolean, partial: (month: string) => boolean) {
  if (!patterns) return
  if (patterns.series.length && patterns.meses.filter(inside).length > 0) views.push({ id: 'product-calendar', label: 'Calendario de productos por ID', category: 'Productos', kind: 'matrix', unit: 'money',
    rows: patterns.series.map(row => Object.fromEntries([['name', row.nombre + ' · ' + row.id], ...row.valores.map(point => [point.mes, point.ventas_netas])]) as ExplorationView['rows'][number]),
    keys: patterns.meses.filter(inside).slice(-18).map(month => ({ key: month, label: month })), evidence: `${patterns.productos_revisados} productos revisados; hasta doce series visibles. ${patterns.limite}`,
    action: 'Distingue ventas puntuales, continuidad y pausas. Revisa disponibilidad y temporada antes de dejar de invertir en un producto.' })
  const peaks = patterns.picos_recurrentes.filter(row => row.evidencia.every(year => Array.from({ length: 12 }, (_, i) => `${year.ano}-${String(i + 1).padStart(2, '0')}`).every(month => inside(month) && !partial(month))))
  for (const [index, peak] of peaks.entries()) views.push({ id: index ? 'recurring-peak-' + peak.id : 'recurring-peak', label: index ? 'Pico anual · ' + peak.nombre : 'Pico anual recurrente observado', category: 'Productos', kind: 'bars', unit: 'percent',
    rows: peak.evidencia.map(row => ({ name: `${monthNames[row.mes - 1]} ${row.ano}`, value: row.participacion_pct })), keys: [{ key: 'value', label: '% de ventas positivas del año' }],
    evidence: `${peak.nombre} (ID ${peak.id}) concentra al menos 30% de sus ventas positivas en ${monthNames[peak.mes - 1]} en ${peak.evidencia.length} años comparables. No demuestra la causa ni predice el próximo año.`,
    action: 'Evalúa reposición y promoción antes de esa temporada. Compara margen, stock y campañas; una pausa fuera de temporada no justifica retirar el producto.' })
}
