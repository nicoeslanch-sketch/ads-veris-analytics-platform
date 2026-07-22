import Card from './ui/Card'
import { formatCLP, formatNumber } from '../lib/format'
import {
  AXIS_INK,
  CATEGORICAL,
  CHART,
  GRID_STROKE,
  chartColorForKey,
  distributionChartKind,
  formatCLPCompact,
  formatMonthShort,
  truncateLabel,
} from '../lib/charts'
import type { MetricsResult } from '../lib/types'
import {
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

type GenericAnalysis = NonNullable<MetricsResult['analisis_generico']>
type GenericNumeric = NonNullable<GenericAnalysis['numericas']>[number]
type GenericDistribution = NonNullable<GenericAnalysis['distribuciones']>[number]

/** Fase 18: los resúmenes adaptativos dejan de ser solo tarjetas — cada perfil
 * (campañas, inventario, clientes, sucursales, trabajadores, metas…) muestra
 * sus distribuciones con gráficos, siempre a partir de columnas reales. */

const GENERIC_TITLES: Record<string, { titulo: string; nota: string }> = {
  clientes: {
    titulo: 'Perfil de clientes',
    nota: 'Esta hoja se interpreta como una maestra de clientes: se resumen sus distribuciones sin inventar ventas.',
  },
  sucursales: {
    titulo: 'Red de sucursales',
    nota: 'Esta hoja se interpreta como una maestra de sucursales: se resumen sus distribuciones sin inventar ventas.',
  },
  trabajadores: {
    titulo: 'Equipo de trabajo',
    nota: 'Esta hoja se interpreta como una nómina o listado de trabajadores: se resumen cargos y montos sin tratarlos como ventas.',
  },
  metas: {
    titulo: 'Metas y objetivos',
    nota: 'Esta hoja se interpreta como metas u objetivos: se resumen sus valores sin tratarlos como ventas reales.',
  },
  productos: {
    titulo: 'Maestra de productos',
    nota: 'Resumen del surtido, categorías, marcas, precios y estado; no se interpreta como venta realizada.',
  },
  proveedores: {
    titulo: 'Red de proveedores',
    nota: 'Cobertura de proveedores, categorías, regiones y condiciones de pago para gestionar abastecimiento.',
  },
  compras: {
    titulo: 'Compras y abastecimiento',
    nota: 'Los montos corresponden a compras. No se presentan como ingresos, ticket de venta ni utilidad.',
  },
  gastos: {
    titulo: 'Gastos operacionales',
    nota: 'Los montos corresponden a egresos operacionales y se analizan por categoría, estado y periodo.',
  },
  cobranzas: {
    titulo: 'Cobranzas y pagos',
    nota: 'Los montos representan pagos recibidos y su estado, no ventas nuevas ni utilidad.',
  },
  historial_costos: {
    titulo: 'Evolución de costos',
    nota: 'Resume costos unitarios por vigencia y fuente; no suma costos unitarios como gasto del negocio.',
  },
}

export default function AdaptiveProfileSummary({
  metrics,
  variant = 'summary',
}: {
  metrics: MetricsResult
  variant?: 'summary' | 'explore'
}) {
  const isExplore = variant === 'explore'
  const campaign = metrics.analisis_campanas
  const inventory = metrics.analisis_inventario
  const generic = metrics.analisis_generico
  if (campaign) {
    const cards: string[][] = [
      ['Campañas', formatNumber(campaign.campanas)],
      ['Inversión', campaign.inversion == null ? '—' : formatCLP(campaign.inversion)],
      ['Impresiones', formatNumber(campaign.impresiones)],
      ['Clics', formatNumber(campaign.clics)],
      ['CTR', campaign.ctr_pct == null ? '—' : `${formatNumber(campaign.ctr_pct)}%`],
      ['CPC', campaign.cpc == null ? '—' : formatCLP(campaign.cpc)],
    ]
    const platforms = (campaign.por_plataforma ?? []).map((item) => ({
      ...item,
      etiqueta: truncateLabel(item.nombre, 18),
    }))
    return (
      <div className="space-y-5">
        <h2 className="text-base font-semibold text-navy">Rendimiento de campañas</h2>
        <PurposeBanner variant={variant} summary="Vista ejecutiva: inversión, alcance y eficiencia para decidir dónde reasignar presupuesto." explore="Vista analítica: compara plataformas, estados y eficiencia para investigar qué explica el resultado." />
        <CardGrid cards={cards} />
        {(campaign.clics_sobre_impresiones ?? 0) > 0 && (
          <p className="rounded-xl border border-gold/30 bg-gold/[0.07] px-4 py-3 text-xs leading-relaxed text-navy/70">
            {formatNumber(campaign.clics_sobre_impresiones ?? 0)} campaña(s) registran más clics
            que impresiones (CTR sobre 100%). Revísalas en el origen: suelen ser errores de
            captura o columnas intercambiadas.
          </p>
        )}
        {platforms.length > 1 && (
          <div className="grid gap-5 xl:grid-cols-2">
            <Card>
              <h3 className="text-sm font-semibold text-navy">Inversión por plataforma</h3>
              <div className="mt-4 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={platforms} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
                    <XAxis type="number" tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="etiqueta" width={110} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip formatter={(value) => formatCLP(Number(value))} />
                    <Bar dataKey="inversion" name="Inversión" fill={CHART.ingresos} radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            {isExplore && (
              <Card>
                <h3 className="text-sm font-semibold text-navy">Clics y CTR por plataforma</h3>
                <div className="mt-4 h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={platforms} margin={{ top: 4, right: 12, bottom: 4, left: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
                      <XAxis dataKey="etiqueta" tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis tickFormatter={(value: number) => formatNumber(value)} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                      <Tooltip formatter={(value, name) => name === 'CTR %' ? `${formatNumber(Number(value))}%` : formatNumber(Number(value))} />
                      <Legend />
                      <Bar dataKey="clics" name="Clics" fill={CHART.flujo} radius={[3, 3, 0, 0]} />
                      <Bar dataKey="ctr_pct" name="CTR %" fill={CHART.utilidad} radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            )}
          </div>
        )}
        {isExplore && (
          <div className="grid gap-4 lg:grid-cols-2">
            <CountList title="Plataformas" rows={campaign.plataformas} />
            <CountList title="Estados" rows={campaign.estados} />
          </div>
        )}
      </div>
    )
  }
  if (inventory) {
    const cards: string[][] = [
      ['Registros', formatNumber(inventory.registros)],
      ['Productos', formatNumber(inventory.productos)],
      ['Stock total', formatNumber(inventory.stock_total)],
      ['Stock mínimo', formatNumber(inventory.stock_minimo_total)],
      ['Bajo mínimo', formatNumber(inventory.bajo_minimo)],
      ['Cobertura', `${formatNumber(inventory.cobertura_stock_pct)}%`],
      ...(inventory.valor_inventario != null
        ? [['Valor de inventario', formatCLP(inventory.valor_inventario)]]
        : []),
      ...(inventory.unidades_comprometidas != null
        ? [['Unidades comprometidas', formatNumber(inventory.unidades_comprometidas)]]
        : []),
      ...(inventory.diferencia_conteo != null
        ? [['Diferencia de conteo', formatNumber(inventory.diferencia_conteo)]]
        : []),
    ]
    const branches = (inventory.por_sucursal ?? []).slice(0, 15).map((item) => ({
      ...item,
      etiqueta: truncateLabel(item.nombre, 16),
    }))
    return (
      <div className="space-y-5">
        <h2 className="text-base font-semibold text-navy">Estado del inventario</h2>
        <PurposeBanner variant={variant} summary="Vista operativa: disponibilidad, quiebres y valor inmovilizado para priorizar reposición." explore="Vista analítica: compara sucursales, cobertura y diferencias para localizar el origen de los quiebres." />
        <CardGrid cards={isExplore ? cards : cards.slice(0, 8)} />
        {(inventory.stocks_negativos ?? 0) > 0 && (
          <p className="rounded-xl border border-gold/30 bg-gold/[0.07] px-4 py-3 text-xs leading-relaxed text-navy/70">
            {formatNumber(inventory.stocks_negativos ?? 0)} registro(s) tienen stock negativo:
            pueden ser ajustes pendientes o errores de captura. Revísalos antes de valorizar
            existencias.
          </p>
        )}
        {branches.length > 1 && (
          <div className="grid gap-5 xl:grid-cols-2">
            <Card>
              <h3 className="text-sm font-semibold text-navy">Stock por sucursal</h3>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={branches} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
                    <XAxis type="number" tickFormatter={(value: number) => formatNumber(value)} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="etiqueta" width={100} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip formatter={(value) => formatNumber(Number(value))} />
                    <Bar dataKey="stock" name="Stock" fill={CHART.ingresos} radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card>
              <h3 className="text-sm font-semibold text-navy">Quiebres por sucursal</h3>
              <p className="mt-1 text-xs text-navy/55">Registros bajo el stock mínimo.</p>
              <div className="mt-4 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={branches} margin={{ top: 4, right: 12, bottom: 4, left: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
                    <XAxis dataKey="etiqueta" tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip formatter={(value) => formatNumber(Number(value))} />
                    <Bar dataKey="bajo_minimo" name="Bajo mínimo" fill={CHART.alerta} radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>
        )}
        {isExplore && (
          <div className="grid gap-4 lg:grid-cols-2">
            <CountList title="Sucursales" rows={inventory.sucursales} />
          </div>
        )}
      </div>
    )
  }
  if (!generic) return null
  const meta = generic.subtipo ? GENERIC_TITLES[generic.subtipo] : null
  const distribuciones = (generic.distribuciones ?? []).slice(0, isExplore ? 6 : 2)
  const numericas = (generic.numericas ?? []).slice(0, isExplore ? 8 : 4)
  const evolution = generic.evolucion

  const formatMetric = (
    item: GenericNumeric,
    value: number | null,
  ) => {
    if (value == null) return '—'
    if (item.formato === 'moneda') return formatCLP(value)
    if (item.formato === 'porcentaje') return `${formatNumber(value)}%`
    return formatNumber(value)
  }
  return (
    <div className="space-y-5">
      <h2 className="text-base font-semibold text-navy">{meta?.titulo ?? 'Perfil estructural'}</h2>
      <PurposeBanner
        variant={variant}
        summary={`Vista ejecutiva: ${meta?.nota ?? 'estado general y señales que requieren atención.'}`}
        explore="Vista analítica: desgloses, rangos y evolución para comparar segmentos y encontrar la causa de los resultados."
      />
      <CardGrid
        cards={[
          ['Registros', formatNumber(generic.registros)],
          ['Columnas', formatNumber(generic.columnas)],
          ['Celdas informadas', `${formatNumber(generic.celdas_informadas_pct)}%`],
        ]}
      />
      {numericas.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {numericas.map((item, index) => {
            const highlighted = item.destacado === 'promedio' ? item.promedio : item.total
            const color = chartColorForKey(item.columna, index)
            return (
              <Card
                key={item.columna}
                className="!p-4"
                style={{ background: `linear-gradient(135deg, ${color}14, #ffffff 62%)` }}
              >
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
                  <p className="truncate text-xs text-navy/55" title={item.columna}>{item.columna}</p>
                </div>
                <p className="mt-2 text-lg font-bold text-navy">{formatMetric(item, highlighted)}</p>
                <p className="mt-1 text-[11px] text-navy/55">
                  {item.destacado === 'promedio' ? 'promedio' : 'total'} · mediana {formatMetric(item, item.mediana)}
                </p>
                {isExplore && (
                  <p className="mt-1 text-[11px] text-navy/50">
                    rango {formatMetric(item, item.minimo)} – {formatMetric(item, item.maximo)}
                    {(item.fuera_rango ?? 0) > 0 ? ` · ${item.fuera_rango} fuera de 0–100%` : ''}
                  </p>
                )}
              </Card>
            )
          })}
        </div>
      )}
      {evolution && evolution.valores.length > 1 && (
        <Card>
          <h3 className="text-sm font-semibold text-navy">
            {evolution.operacion === 'promedio' ? 'Promedio' : 'Total'} mensual · {evolution.columna}
          </h3>
          <p className="mt-1 text-xs text-navy/55">
            {isExplore
              ? 'Serie temporal para comparar periodos y localizar cambios.'
              : 'Tendencia principal para anticipar desvíos operativos.'}
          </p>
          <div className="mt-4 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={evolution.valores} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
                <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                <XAxis dataKey="mes" tickFormatter={formatMonthShort} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={evolution.formato === 'moneda' ? formatCLPCompact : (value: number) => formatNumber(value)} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} width={62} />
                <Tooltip formatter={(value) => evolution.formato === 'moneda' ? formatCLP(Number(value)) : evolution.formato === 'porcentaje' ? `${formatNumber(Number(value))}%` : formatNumber(Number(value))} labelFormatter={(label) => formatMonthShort(String(label))} />
                <Line type="monotone" dataKey="valor" name={evolution.columna} stroke={chartColorForKey(evolution.columna)} strokeWidth={2.5} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
      {distribuciones.length > 0 && (
        <div className="grid gap-5 xl:grid-cols-2">
          {distribuciones.map((distro, index) => (
            <DistributionCard key={distro.columna} distro={distro} color={chartColorForKey(distro.columna, index)} />
          ))}
        </div>
      )}
      {isExplore && (
        <Card>
          <h3 className="text-sm font-semibold text-navy">Diccionario rápido de la hoja</h3>
          <p className="mt-1 text-xs text-navy/50">Campos disponibles para profundizar o ajustar el mapeo.</p>
          <p className="mt-2 text-xs leading-6 text-navy/65">{generic.columnas_disponibles.join(' · ')}</p>
        </Card>
      )}
    </div>
  )
}

function PurposeBanner({
  variant,
  summary,
  explore,
}: {
  variant: 'summary' | 'explore'
  summary: string
  explore: string
}) {
  const isExplore = variant === 'explore'
  return (
    <div className={`rounded-xl border px-4 py-3 ${isExplore ? 'border-navy/15 bg-navy/[0.035]' : 'border-teal/20 bg-teal/[0.05]'}`}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-navy/45">
        {isExplore ? 'Explorar · entender causas' : 'Resumen · decidir y priorizar'}
      </p>
      <p className="mt-1 text-xs leading-relaxed text-navy/70">{isExplore ? explore : summary}</p>
    </div>
  )
}

function DistributionCard({
  distro,
  color,
}: {
  distro: GenericDistribution
  color: string
}) {
  const rows = distro.valores.map((valor) => ({
    ...valor,
    etiqueta: truncateLabel(valor.nombre, 18),
  }))
  const chartKind = distributionChartKind(rows)
  return (
    <Card>
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
        <h3 className="text-sm font-semibold text-navy">{distro.columna}</h3>
      </div>
      <p className="mt-1 text-xs text-navy/55">
        Registros por valor{distro.valores_totales > rows.length ? ` (top ${rows.length} de ${distro.valores_totales})` : ''}.
      </p>
      <div className="mt-4" style={{ height: chartKind === 'donut' ? 250 : Math.max(rows.length * 28 + 40, 160) }}>
        <ResponsiveContainer width="100%" height="100%">
          {chartKind === 'donut' ? (
            <PieChart>
              <Pie data={rows} dataKey="registros" nameKey="etiqueta" innerRadius={55} outerRadius={88} paddingAngle={2}>
                {rows.map((row, index) => (
                  <Cell key={`${row.nombre}-${index}`} fill={CATEGORICAL[index % CATEGORICAL.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => formatNumber(Number(value))} />
              <Legend />
            </PieChart>
          ) : (
            <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
              <XAxis type="number" allowDecimals={false} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="etiqueta" width={120} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip formatter={(value) => formatNumber(Number(value))} />
              <Bar dataKey="registros" name="Registros" fill={color} radius={[0, 4, 4, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function CardGrid({ cards }: { cards: string[][] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {cards.map(([label, value], index) => {
        const color = chartColorForKey(label, index)
        return (
          <Card key={label} className="!p-4" style={{ background: `linear-gradient(135deg, ${color}12, #ffffff 62%)` }}>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
              <p className="text-xs text-navy/50">{label}</p>
            </div>
            <p className="mt-1 text-lg font-bold text-navy">{value}</p>
          </Card>
        )
      })}
    </div>
  )
}

function CountList({ title, rows }: { title: string; rows: Array<{ nombre: string; registros: number }> }) {
  if (!rows.length) return null
  return (
    <Card>
      <h3 className="text-sm font-semibold text-navy">{title}</h3>
      <div className="mt-3 space-y-2">
        {rows.map((row) => (
          <div key={row.nombre} className="flex justify-between text-xs">
            <span>{row.nombre}</span>
            <strong>{formatNumber(row.registros)}</strong>
          </div>
        ))}
      </div>
    </Card>
  )
}
