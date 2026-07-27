import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
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
import {
  AXIS_INK,
  CATEGORICAL,
  GRID_STROKE,
  truncateLabel,
} from '../lib/charts'
import { formatCLP, formatNumber } from '../lib/format'
import type {
  BusinessAnalysis,
  BusinessIndicator,
  BusinessIndicatorCategory,
} from '../lib/types'

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
      <p className="mt-2 break-words text-lg font-bold leading-tight text-navy">
        {indicatorValue(indicator)}
      </p>
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

function CategorySummary({ category }: { category: BusinessIndicatorCategory }) {
  const meta = categoryMeta(category.id)
  const Icon = meta.icon
  return (
    <div className={[
      'min-h-[64px] rounded-lg border px-3 py-3 transition-colors',
      category.disponibles > 0
        ? 'border-navy/10 bg-white hover:border-teal/30'
        : 'border-navy/5 bg-navy/[0.025]',
    ].join(' ')}>
      <div className="flex items-center gap-2">
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
          style={{ color: meta.color, backgroundColor: `${meta.color}16` }}
        >
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <p className="line-clamp-2 text-xs font-semibold leading-tight text-navy">{category.nombre}</p>
          <p className="text-[10px] text-navy/45">
            {category.disponibles} de {category.total} habilitados
          </p>
        </div>
      </div>
    </div>
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
    <Card className="min-w-0">
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
  const rows = (analysis.agrupaciones[selected.key] ?? [])
    .filter((row) => row.ingresos != null)
    .slice(0, 8)
    .map((row) => ({ ...row, etiqueta: truncateLabel(row.nombre, 20) }))
  return (
    <Card className="min-w-0 xl:col-span-2">
      <h3 className="text-sm font-semibold text-navy">{selected.title}</h3>
      <p className="mt-1 text-[11px] text-navy/50">
        El gráfico se adapta a la primera dimensión confiable disponible; la utilidad solo aparece donde existe costo pareado.
      </p>
      <div style={{ height: Math.max(230, rows.length * 34 + 54) }} className="mt-3">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
            <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
            <XAxis type="number" tickFormatter={(value) => formatCurrencyCompact(Number(value), currency)} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="etiqueta" width={130} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip formatter={(value) => formatCurrency(Number(value), currency)} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="ingresos" name="Ventas netas" radius={[0, 3, 3, 0]}>
              {rows.map((row, index) => (
                <Cell key={row.nombre} fill={CATEGORICAL[index % CATEGORICAL.length]} />
              ))}
            </Bar>
            <Bar dataKey="utilidad" name="Utilidad conocida" fill="#24966d" radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

export default function AdaptiveIndicatorCatalog({ analysis }: { analysis: BusinessAnalysis }) {
  const catalog = analysis.catalogo_indicadores
  if (!catalog) return null
  const enabled = catalog.categorias
    .flatMap((category) => category.indicadores)
    .filter((indicator) => indicator.estado === 'available' || indicator.estado === 'partial')
  const priority = [
    'ventas_ultimo_mes_completo',
    'ticket_promedio_documento',
    'unidades_vendidas',
    'cobertura_costos_pct',
    'cuentas_por_cobrar',
    'cobranza_vencida',
    'stock_valorizado',
    'rotacion_inventario',
    'compras_netas',
    'concentracion_cliente_principal',
    'cumplimiento_meta_ventas',
    'conversion_marketing',
  ]
  const highlights = priority
    .map((id) => enabled.find((indicator) => indicator.id === id))
    .filter((indicator): indicator is BusinessIndicator => Boolean(indicator))
    .slice(0, 8)
  const receivables = analysis.operacion.cuentas_por_cobrar
  const overdue = analysis.operacion.cuentas_vencidas
  const expenseFixed = analysis.operacion.gastos_fijos
  const expenseVariable = analysis.operacion.gastos_variables
  const monetaryChartsAllowed = catalog.moneda !== 'mixta'

  return (
    <section className="space-y-4" aria-labelledby="adaptive-indicators-title">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-teal">
              Catálogo adaptativo
            </p>
            <h2 id="adaptive-indicators-title" className="mt-1 text-base font-semibold text-navy">
              Indicadores habilitados por este libro
            </h2>
            <p className="mt-1 max-w-3xl text-xs leading-relaxed text-navy/55">
              ADS Veris elige cálculos y gráficos según las hojas, campos y relaciones realmente disponibles.
              Un indicador sin base suficiente se explica; nunca se inventa ni convierte un dato faltante en cero.
            </p>
          </div>
          <div className="flex gap-2 text-[10px]">
            <span className="rounded-full bg-green/10 px-2.5 py-1 font-semibold text-green">
              {catalog.disponibles} disponibles
            </span>
            <span className="rounded-full bg-gold/15 px-2.5 py-1 font-semibold text-amber-700">
              {catalog.parciales} parciales
            </span>
            <span className="rounded-full bg-navy/7 px-2.5 py-1 font-semibold text-navy/50">
              {catalog.no_disponibles} por conectar
            </span>
          </div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {catalog.categorias.map((category) => (
            <CategorySummary key={category.id} category={category} />
          ))}
        </div>
      </Card>

      {highlights.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {highlights.map((indicator) => (
            <IndicatorCard key={indicator.id} indicator={indicator} />
          ))}
        </div>
      )}

      <div className="grid items-start gap-4 xl:grid-cols-2">
        {monetaryChartsAllowed && (
          <ContributionPanel analysis={analysis} currency={catalog.moneda} />
        )}
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
        {monetaryChartsAllowed && expenseFixed != null && expenseVariable != null && expenseFixed + expenseVariable > 0 && (
          <DonutPanel
            title="Estructura de gastos operacionales"
            subtitle="Solo se clasifica cuando el libro declara gasto fijo o variable."
            rows={[
              { nombre: 'Fijos', valor: expenseFixed },
              { nombre: 'Variables', valor: expenseVariable },
            ]}
            currency={catalog.moneda}
          />
        )}
      </div>
    </section>
  )
}
