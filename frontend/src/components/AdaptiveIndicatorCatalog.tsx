import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  BadgeDollarSign,
  Banknote,
  Boxes,
  BriefcaseBusiness,
  ChartNoAxesCombined,
  CircleGauge,
  HandCoins,
  PackageSearch,
  ReceiptText,
  UsersRound,
} from 'lucide-react'
import Card from './ui/Card'
import KpiCarousel from './ui/KpiCarousel'
import KpiValue from './ui/KpiValue'
import {
  AXIS_INK,
  CATEGORICAL,
  CHART,
  GRID_STROKE,
  truncateLabel,
} from '../lib/charts'
import { formatCLP, formatNumber } from '../lib/format'
import type { BusinessAnalysis, BusinessIndicator } from '../lib/types'
import type { BusinessGroupRow } from '../lib/types'

const CATEGORY_META = {
  ventas: { color: '#0ea5a8', icon: ChartNoAxesCombined },
  rentabilidad: { color: '#3281c7', icon: BadgeDollarSign },
  caja: { color: '#8559c7', icon: Banknote },
  cobranza: { color: '#e76651', icon: HandCoins },
  inventario: { color: '#779d37', icon: Boxes },
  clientes: { color: '#d69a19', icon: UsersRound },
  compras: { color: '#3378b8', icon: PackageSearch },
  gastos: { color: '#d65b43', icon: ReceiptText },
  comercial: { color: '#4b9b5e', icon: BriefcaseBusiness },
  balance: { color: '#7354a8', icon: CircleGauge },
} as const

function categoryMeta(category: string) {
  return CATEGORY_META[category as keyof typeof CATEGORY_META] ?? {
    color: '#0ea5a8',
    icon: CircleGauge,
  }
}

function indicatorValue(indicator: BusinessIndicator) {
  if (indicator.valor == null) return 'No disponible'
  const currency = indicator.unidad.split('/')[0]
  if (/^[A-Z]{3}$/.test(currency)) {
    const formatted = formatCurrency(indicator.valor, currency)
    return indicator.unidad.includes('/documento') ? `${formatted}/documento` : formatted
  }
  if (indicator.unidad === '%') return `${formatNumber(indicator.valor)}%`
  if (indicator.unidad === 'días') return `${formatNumber(indicator.valor)} días`
  if (indicator.unidad === 'veces') return `${formatNumber(indicator.valor)}x`
  return `${formatNumber(indicator.valor)} ${indicator.unidad}`
}

function formatCurrency(value: number, currency: string) {
  try {
    return new Intl.NumberFormat('es-CL', {
      style: 'currency',
      currency,
      currencyDisplay: 'narrowSymbol',
      maximumFractionDigits: 0,
    }).format(value)
  } catch {
    return formatCLP(value)
  }
}

function formatCurrencyCompact(value: number, currency: string) {
  try {
    return new Intl.NumberFormat('es-CL', {
      style: 'currency',
      currency,
      currencyDisplay: 'narrowSymbol',
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value)
  } catch {
    return formatCLP(value)
  }
}

function variationText(indicator: BusinessIndicator) {
  if (indicator.variacion == null) return null
  const suffix = indicator.tipo_variacion === 'puntos_porcentuales' ? ' pp' : '%'
  return `${indicator.variacion >= 0 ? '↑' : '↓'} ${formatNumber(Math.abs(indicator.variacion))}${suffix}`
}

function statusLabel(status: BusinessIndicator['estado']) {
  if (status === 'available') return 'Disponible'
  if (status === 'partial') return 'Parcial'
  if (status === 'blocked') return 'Bloqueado'
  return 'Faltan datos'
}

function IndicatorCard({ indicator }: { indicator: BusinessIndicator }) {
  const meta = categoryMeta(indicator.categoria)
  const variation = variationText(indicator)
  const favorable = indicator.variacion != null && (
    indicator.polaridad === 'lower_is_better'
      ? indicator.variacion <= 0
      : indicator.variacion >= 0
  )
  return (
    <article
      className="rounded-lg border border-navy/10 p-3.5"
      style={{ background: `linear-gradient(145deg, ${meta.color}12, #fff 72%)` }}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-navy/50">
          {indicator.nombre}
        </p>
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ backgroundColor: meta.color }}
        />
      </div>
      <KpiValue value={indicatorValue(indicator)} maxPx={22} className="mt-2" />
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px]">
        <span className={[
          'rounded-full px-2 py-0.5 font-semibold',
          indicator.estado === 'available'
            ? 'bg-green/10 text-green'
            : indicator.estado === 'partial'
              ? 'bg-gold/15 text-amber-700'
              : 'bg-navy/7 text-navy/45',
        ].join(' ')}>
          {statusLabel(indicator.estado)}
        </span>
        {variation && (
          <span className={favorable ? 'font-semibold text-green' : 'font-semibold text-coral'}>
            {variation} vs anterior
          </span>
        )}
        {indicator.cobertura_datos_pct != null && (
          <span className="text-navy/45">
            Cobertura {formatNumber(indicator.cobertura_datos_pct)}%
          </span>
        )}
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-navy/45">
        {indicator.formula}
      </p>
      {indicator.advertencias[0] && (
        <p className="mt-2 rounded-md bg-gold/[0.10] px-2 py-1.5 text-[10px] leading-relaxed text-navy/60">
          {indicator.advertencias[0]}
        </p>
      )}
    </article>
  )
}

function DonutPanel({
  title,
  subtitle,
  rows,
  currency,
}: {
  title: string
  subtitle: string
  rows: Array<{ nombre: string; valor: number }>
  currency: string
}) {
  const safeRows = rows.filter((row) => Number.isFinite(row.valor) && row.valor >= 0)
  const total = safeRows.reduce((sum, row) => sum + row.valor, 0)
  if (!safeRows.length || total <= 0) return null
  return (
    <Card className="min-w-0 xl:col-span-2">
      <h3 className="text-sm font-semibold text-navy">{title}</h3>
      <p className="mt-1 text-[11px] text-navy/50">{subtitle}</p>
      <div className="mt-3 grid items-center gap-3 sm:grid-cols-[180px_1fr]">
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={safeRows} dataKey="valor" nameKey="nombre" innerRadius={45} outerRadius={72}>
                {safeRows.map((row, index) => (
                  <Cell key={row.nombre} fill={CATEGORICAL[index % CATEGORICAL.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => formatCurrency(Number(value), currency)} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="space-y-2">
          {safeRows.map((row, index) => (
            <li key={row.nombre} className="flex items-center justify-between gap-3 text-xs">
              <span className="flex items-center gap-2 text-navy/65">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ background: CATEGORICAL[index % CATEGORICAL.length] }}
                />
                {row.nombre}
              </span>
              <span className="font-semibold text-navy">{formatCurrency(row.valor, currency)}</span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  )
}

export function compactContributionRows(
  sourceRows: BusinessGroupRow[],
  visibleLimit = 12,
): BusinessGroupRow[] {
  if (sourceRows.length <= visibleLimit) return sourceRows
  return [
    ...sourceRows.slice(0, visibleLimit - 1),
    sourceRows.slice(visibleLimit - 1).reduce((other, row) => ({
      ...other,
      ingresos: other.ingresos + row.ingresos,
      ingresos_positivos: (other.ingresos_positivos ?? 0) + (row.ingresos_positivos ?? 0),
      costo: other.costo == null && row.costo == null
        ? null
        : (other.costo ?? 0) + (row.costo ?? 0),
      utilidad: other.utilidad == null && row.utilidad == null
        ? null
        : (other.utilidad ?? 0) + (row.utilidad ?? 0),
      filas: other.filas + row.filas,
      filas_pareadas: other.filas_pareadas + row.filas_pareadas,
    }), {
      nombre: `Otros (${sourceRows.length - visibleLimit + 1})`,
      ingresos: 0,
      ingresos_positivos: 0,
      participacion_pct: null,
      costo: null,
      utilidad: null,
      margen_pct: null,
      filas: 0,
      filas_pareadas: 0,
      cobertura_costos_pct: 0,
    }),
  ]
}

function ContributionPanel({
  analysis,
  currency,
}: {
  analysis: BusinessAnalysis
  currency: string
}) {
  const candidates = [
    { key: 'categorias', title: 'Ventas y utilidad por categoría' },
    { key: 'canales', title: 'Ventas y utilidad por canal' },
    { key: 'sucursales', title: 'Ventas y utilidad por sucursal' },
    { key: 'productos', title: 'Ventas y utilidad por producto' },
  ]
  const selected = candidates.find(({ key }) => (
    (analysis.agrupaciones[key] ?? []).filter((row) => row.ingresos != null).length > 1
  ))
  if (!selected) return null
  const sourceRows = (analysis.agrupaciones[selected.key] ?? [])
    .filter((row) => row.ingresos != null)
  const rows = compactContributionRows(sourceRows)
    .map((row) => ({ ...row, etiqueta: truncateLabel(row.nombre, 20) }))
  const visibleSales = rows.reduce((sum, row) => sum + row.ingresos, 0)
  return (
    <Card className="min-w-0 xl:col-span-2">
      <h3 className="text-sm font-semibold text-navy">{selected.title}</h3>
      <p className="mt-1 text-[11px] text-navy/50">
        El gráfico se adapta a la primera dimensión confiable disponible; la utilidad solo aparece donde existe costo pareado. Total visible: {formatCurrency(visibleSales, currency)}.
      </p>
      <div style={{ height: Math.max(230, rows.length * 34 + 54) }} className="mt-3">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
            <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
            <XAxis type="number" tickFormatter={(value) => formatCurrencyCompact(Number(value), currency)} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="etiqueta" width={130} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip formatter={(value) => formatCurrency(Number(value), currency)} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="ingresos" name="Ventas netas" fill={CHART.ingresos} radius={[0, 3, 3, 0]} />
            <Bar dataKey="utilidad" name="Utilidad conocida" fill={CHART.utilidad} radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function ExpenseBreakdownPanel({ analysis, currency }: { analysis: BusinessAnalysis; currency: string }) {
  const sourceRows = analysis.desgloses?.gastos_operacionales ?? []
  if (!sourceRows.length) return null
  const limit = 16
  const rows = (sourceRows.length <= limit
    ? sourceRows
    : [
        ...sourceRows.slice(0, limit - 1),
        sourceRows.slice(limit - 1).reduce((other, row) => ({
          nombre: `Otros (${sourceRows.length - limit + 1})`,
          fijo: other.fijo + row.fijo,
          variable: other.variable + row.variable,
          sin_clasificar: other.sin_clasificar + row.sin_clasificar,
          total: other.total + row.total,
          registros: other.registros + row.registros,
        }), {
          nombre: '', fijo: 0, variable: 0, sin_clasificar: 0, total: 0, registros: 0,
        }),
      ])
    .map((row) => ({ ...row, etiqueta: truncateLabel(row.nombre, 24) }))
  return (
    <Card className="min-w-0 xl:col-span-2">
      <h3 className="text-sm font-semibold text-navy">Gastos operacionales por categoría</h3>
      <p className="mt-1 text-[11px] text-navy/50">
        Montos del mismo periodo y base del resultado operacional; fijo y variable se distinguen por color.
      </p>
      <div className="mt-3" style={{ height: Math.max(280, rows.length * 34 + 58) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 18, bottom: 4, left: 12 }}>
            <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
            <XAxis type="number" tickFormatter={(value) => formatCurrencyCompact(Number(value), currency)} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="etiqueta" width={150} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip formatter={(value) => formatCurrency(Number(value), currency)} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="fijo" stackId="gasto" name="Fijo" fill={CHART.gastos} radius={[0, 0, 0, 0]} />
            <Bar dataKey="variable" stackId="gasto" name="Variable" fill={CATEGORICAL[2]} />
            <Bar dataKey="sin_clasificar" stackId="gasto" name="Sin clasificación" fill="#a6adbb" radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function SellerProfitPanel({ analysis, currency }: { analysis: BusinessAnalysis; currency: string }) {
  const rows = (analysis.agrupaciones.vendedores ?? [])
    .filter((row) => row.utilidad != null && row.nombre.toLocaleLowerCase('es-CL') !== 'sin clasificar')
    .sort((left, right) => (right.utilidad ?? 0) - (left.utilidad ?? 0))
    .slice(0, 12)
    .map((row) => ({ ...row, etiqueta: truncateLabel(row.nombre, 22) }))
  if (rows.length < 2) return null
  return (
    <Card className="min-w-0">
      <h3 className="text-sm font-semibold text-navy">Ranking de vendedores por utilidad</h3>
      <p className="mt-1 text-[11px] text-navy/50">Sólo ventas con costo histórico relacionado.</p>
      <div className="mt-3" style={{ height: Math.max(260, rows.length * 32 + 52) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 14, bottom: 4, left: 8 }}>
            <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
            <XAxis type="number" tickFormatter={(value) => formatCurrencyCompact(Number(value), currency)} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="etiqueta" width={135} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip formatter={(value) => formatCurrency(Number(value), currency)} />
            <Bar dataKey="utilidad" name="Utilidad conocida" fill={CHART.utilidad} radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function BranchSalesMarginPanel({ analysis, currency }: { analysis: BusinessAnalysis; currency: string }) {
  const rows = (analysis.agrupaciones.sucursales ?? [])
    .filter((row) => row.ingresos != null && row.margen_pct != null && row.nombre.toLocaleLowerCase('es-CL') !== 'sin clasificar')
    .slice(0, 12)
    .map((row) => ({ ...row, etiqueta: truncateLabel(row.nombre, 16) }))
  if (rows.length < 2) return null
  return (
    <Card className="min-w-0">
      <h3 className="text-sm font-semibold text-navy">Ventas y margen por sucursal</h3>
      <p className="mt-1 text-[11px] text-navy/50">Barras: venta neta. Línea: margen bruto sobre ventas con costo relacionado.</p>
      <div className="mt-3 h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 30, left: 4 }}>
            <CartesianGrid stroke={GRID_STROKE} vertical={false} />
            <XAxis dataKey="etiqueta" angle={-22} textAnchor="end" height={55} interval={0} tick={{ fill: AXIS_INK, fontSize: 9 }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="money" tickFormatter={(value) => formatCurrencyCompact(Number(value), currency)} tick={{ fill: AXIS_INK, fontSize: 10 }} width={62} axisLine={false} tickLine={false} />
            <YAxis yAxisId="margin" orientation="right" tickFormatter={(value) => `${formatNumber(Number(value))}%`} tick={{ fill: AXIS_INK, fontSize: 10 }} width={40} axisLine={false} tickLine={false} />
            <Tooltip formatter={(value, name) => String(name).startsWith('Margen') ? `${formatNumber(Number(value))}%` : formatCurrency(Number(value), currency)} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar yAxisId="money" dataKey="ingresos" name="Ventas netas" fill={CHART.ingresos} radius={[3, 3, 0, 0]} maxBarSize={34} />
            <Line yAxisId="margin" type="monotone" dataKey="margen_pct" name="Margen bruto" stroke={CHART.utilidad} strokeWidth={2.5} dot={{ r: 3 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function ReturnsByReasonPanel({ analysis, currency }: { analysis: BusinessAnalysis; currency: string }) {
  const rows = (analysis.desgloses?.devoluciones_por_motivo ?? [])
    .slice(0, 12)
    .map((row) => ({ ...row, etiqueta: truncateLabel(row.nombre, 24) }))
  if (rows.length < 2) return null
  return (
    <Card className="min-w-0 xl:col-span-2">
      <h3 className="text-sm font-semibold text-navy">Devoluciones por motivo</h3>
      <p className="mt-1 text-[11px] text-navy/50">Sólo devoluciones aceptadas; muestra monto devuelto y cantidad de casos.</p>
      <div className="mt-3" style={{ height: Math.max(250, rows.length * 34 + 54) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 72, bottom: 4, left: 8 }}>
            <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
            <XAxis type="number" tickFormatter={(value) => formatCurrencyCompact(Number(value), currency)} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="etiqueta" width={150} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip formatter={(value, name, item) => name === 'Monto devuelto' ? [formatCurrency(Number(value), currency), name, `Casos: ${item.payload.casos}`] : value} />
            <Bar dataKey="monto" name="Monto devuelto" fill={CHART.alerta} radius={[0, 3, 3, 0]}>
              <LabelList dataKey="casos" position="right" formatter={(value: unknown) => `${formatNumber(Number(value))} casos`} style={{ fill: AXIS_INK, fontSize: 10 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

type CatalogSection = 'all' | 'highlights' | 'commercial' | 'contribution' | 'commercialDetails' | 'technical'

export default function AdaptiveIndicatorCatalog({
  analysis,
  section = 'all',
}: {
  analysis: BusinessAnalysis
  section?: CatalogSection
}) {
  const catalog = analysis.catalogo_indicadores
  if (!catalog) return null
  const enabled = catalog.categorias
    .flatMap((category) => category.indicadores)
    .filter((indicator) => indicator.estado === 'available' || indicator.estado === 'partial')
  // Orden de relevancia para una PyME: primero lo que mide el resultado y la
  // caja; los promedios por documento y las métricas de detalle van al final
  // (se alcanzan deslizando, sin ocupar la primera pantalla).
  const priority = [
    'ventas_ultimo_mes_completo',
    'cobertura_costos_pct',
    'cuentas_por_cobrar',
    'cobranza_vencida',
    'stock_valorizado',
    'rotacion_inventario',
    'compras_netas',
    'unidades_vendidas',
    'concentracion_cliente_principal',
    'cumplimiento_meta_ventas',
    'ticket_promedio_documento',
    'conversion_marketing',
  ]
  const highlights = priority
    .map((id) => enabled.find((indicator) => indicator.id === id))
    .filter((indicator): indicator is BusinessIndicator => Boolean(indicator))
    .slice(0, 10)
  const receivables = analysis.operacion.cuentas_por_cobrar
  const overdue = analysis.operacion.cuentas_vencidas
  const monetaryChartsAllowed = catalog.moneda !== 'mixta'
  const showHighlights = section === 'all' || section === 'highlights'
  const showContribution = section === 'all' || section === 'commercial' || section === 'contribution'
  const showCommercialDetails = section === 'all' || section === 'commercial' || section === 'commercialDetails'
  const showTechnical = section === 'all' || section === 'technical'

  return (
    <section className="space-y-4">
      {/* El recuadro "Catálogo adaptativo" (conteos y resumen por categoría)
          se retiró: ocupaba una pantalla entera para describir el mecanismo en
          vez de mostrar resultados. La selección adaptativa sigue intacta —
          abajo solo aparecen los indicadores que este libro puede calcular. */}
      {showHighlights && highlights.length > 0 && (
        <KpiCarousel label="Indicadores habilitados por este libro">
          {highlights.map((indicator) => (
            <IndicatorCard key={indicator.id} indicator={indicator} />
          ))}
        </KpiCarousel>
      )}

      {showContribution && <div className="grid items-start gap-4 xl:grid-cols-2">
        {monetaryChartsAllowed && (
          <ContributionPanel analysis={analysis} currency={catalog.moneda} />
        )}
      </div>}

      {showCommercialDetails && <div className="grid items-start gap-4 xl:grid-cols-2">
        {monetaryChartsAllowed && <SellerProfitPanel analysis={analysis} currency={catalog.moneda} />}
        {monetaryChartsAllowed && <BranchSalesMarginPanel analysis={analysis} currency={catalog.moneda} />}
        {monetaryChartsAllowed && <ReturnsByReasonPanel analysis={analysis} currency={catalog.moneda} />}
      </div>}

      {showTechnical && <div className="grid items-start gap-4 xl:grid-cols-2">
        {monetaryChartsAllowed && <ExpenseBreakdownPanel analysis={analysis} currency={catalog.moneda} />}
        {monetaryChartsAllowed && receivables != null && overdue != null && (
          <DonutPanel
            title="Composición de la cobranza"
            subtitle="Saldo abierto vigente y vencido; menor vencido es mejor."
            rows={[
              { nombre: 'Vigente', valor: Math.max(receivables - overdue, 0) },
              { nombre: 'Vencida', valor: overdue },
            ]}
            currency={catalog.moneda}
          />
        )}
      </div>}
    </section>
  )
}
