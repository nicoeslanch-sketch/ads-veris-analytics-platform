import Card from './ui/Card'
import { formatCLP, formatNumber } from '../lib/format'
import { AXIS_INK, CATEGORICAL, CHART, GRID_STROKE, formatCLPCompact, truncateLabel } from '../lib/charts'
import type { MetricsResult } from '../lib/types'
import {
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

type ProductAnalysis = NonNullable<MetricsResult['analisis_productos']>

function money(value: number | null) {
  return value == null ? '\u2014' : formatCLP(value)
}

function pct(value: number | null) {
  return value == null ? '\u2014' : `${formatNumber(value)}%`
}

export default function ProductCatalogSummary({
  analysis,
  variant = 'summary',
}: {
  analysis: ProductAnalysis
  variant?: 'summary' | 'explore'
}) {
  const isExplore = variant === 'explore'
  const hasCosts = analysis.costos.promedio != null
  const totals = analysis.totales_catalogo_unitario
  const costReference = analysis.referencia_tipo === 'costo_total_unitario'
  const referenceLabel = costReference ? 'Costo total unitario' : 'Precio lista'
  const differenceLabel = costReference ? 'Componente adicional' : 'Margen potencial'
  const cards = [
    ['Productos', formatNumber(analysis.productos)],
    ...(hasCosts
      ? [
          ['Costo promedio', money(analysis.costos.promedio)],
          ['Costo mediano', money(analysis.costos.mediana)],
          ['Rango de costo', `${money(analysis.costos.minimo)} - ${money(analysis.costos.maximo)}`],
        ]
      : []),
    [`${referenceLabel} promedio`, money(analysis.precios_lista.promedio)],
    [`${differenceLabel} promedio`, pct(analysis.margen_potencial.promedio)],
    ...(hasCosts ? [['Cobertura de costos', `${formatNumber(analysis.cobertura_costo_pct)}%`]] : []),
    ...(analysis.activos != null || analysis.inactivos != null
      ? [['Estado', `${formatNumber(analysis.activos ?? 0)} activos - ${formatNumber(analysis.inactivos ?? 0)} inactivos`]]
      : []),
    ...(totals
      ? [
          ['Costo catálogo (1 unidad/SKU)', money(totals.costo)],
          [`${referenceLabel} catálogo (1 unidad/SKU)`, money(totals.precio_lista)],
          [`${differenceLabel} (1 unidad/SKU)`, money(totals.utilidad_potencial)],
        ]
      : []),
  ]
  const typicalComparison = analysis.ranking_costos.filter((item) => !item.requiere_revision)
  const comparisonSource = typicalComparison.length ? typicalComparison : analysis.ranking_costos
  const comparison = comparisonSource.slice(0, 10).map((item) => ({
    ...item,
    etiqueta: truncateLabel(item.producto, 22),
  }))
  return (
    <div className="space-y-6">
      <div className={`rounded-xl border px-4 py-3 ${isExplore ? 'border-navy/15 bg-navy/[0.035]' : 'border-teal/20 bg-teal/[0.05]'}`}>
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-navy/45">
          {isExplore ? 'Explorar · comparar productos' : 'Resumen · decidir sobre el catálogo'}
        </p>
        <p className="mt-1 text-xs leading-relaxed text-navy/70">
          {isExplore
            ? 'Profundiza en precios, costos, rangos, marcas y categorías; los valores atípicos siguen visibles y señalados.'
            : 'Prioriza cobertura, estado y referencias de precio/costo. Ningún precio unitario se presenta como venta real.'}
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {(isExplore ? cards : cards.slice(0, 8)).map(([label, value], index) => (
          <Card key={label} className="!p-4" style={{ background: `linear-gradient(135deg, ${CATEGORICAL[index % CATEGORICAL.length]}12, #ffffff 62%)` }}>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: CATEGORICAL[index % CATEGORICAL.length] }} />
              <p className="text-xs text-navy/50">{label}</p>
            </div>
            <p className="mt-1 text-lg font-bold text-navy">{value}</p>
          </Card>
        ))}
      </div>
      <p className="rounded-xl border border-teal/20 bg-teal/5 px-4 py-3 text-xs leading-relaxed text-navy/65">
        Los totales de catálogo suponen una unidad de cada producto. No representan inventario
        ni gasto real; para valorizar existencias se necesita relacionar la cantidad en stock.
      </p>
      {(analysis.costos_a_revisar?.registros ?? 0) > 0 && (
        <p className="rounded-xl border border-gold/35 bg-gold/[0.08] px-4 py-3 text-xs leading-relaxed text-navy/70">
          {formatNumber(analysis.costos_a_revisar?.registros ?? 0)} costo(s) requieren revisión:
          {' '}{formatNumber(analysis.costos_a_revisar?.no_positivos ?? 0)} no positivos y{' '}
          {formatNumber(analysis.costos_a_revisar?.sobre_limite_iqr ?? 0)} sobre el límite IQR.
          Se conservan en las métricas; el gráfico comparativo usa la vista típica y los omite de forma explícita para no aplastar la escala.
        </p>
      )}
      {comparison.length > 0 && (
        <Card>
          <h2 className="text-sm font-semibold text-navy">Costo unitario vs. {referenceLabel.toLowerCase()}</h2>
          <p className="mt-1 text-xs text-navy/55">
            Los 10 productos con mayor costo unitario{(analysis.costos_a_revisar?.registros ?? 0) > 0 ? ' dentro del rango típico' : ''}.
          </p>
          <div className="mt-4 h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={comparison} layout="vertical" margin={{ top: 4, right: 20, bottom: 8, left: 12 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
                <XAxis
                  type="number"
                  tickFormatter={formatCLPCompact}
                  tick={{ fill: AXIS_INK, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="etiqueta"
                  width={150}
                  tick={{ fill: AXIS_INK, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip formatter={(value) => formatCLP(Number(value))} />
                <Legend />
                <Bar dataKey="costo" name="Costo unitario" fill={CHART.gastos} radius={[0, 3, 3, 0]} />
                <Bar dataKey="precio_lista" name={referenceLabel} fill={CHART.ingresos} radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
      <div className="grid gap-5 xl:grid-cols-3">
        {isExplore && analysis.ranking_costos.length > 0 && (
          <Card>
            <h2 className="text-sm font-semibold text-navy">Ranking por costo unitario</h2>
            <div className="mt-3 space-y-2">
              {analysis.ranking_costos.slice(0, 10).map((item, index) => (
                <div key={`${item.producto}-${index}`} className="flex items-center gap-3 text-xs">
                  <span className="w-5 text-navy/40">{index + 1}</span>
                  <span className="min-w-0 flex-1 truncate font-semibold text-navy">{item.producto}</span>
                  <span className={item.requiere_revision ? 'font-semibold text-coral' : 'text-navy/65'}>{money(item.costo)}</span>
                </div>
              ))}
            </div>
          </Card>
        )}
        <CatalogComposition title="Categorías" rows={analysis.categorias} />
        {isExplore && <CatalogComposition title="Marcas" rows={analysis.marcas} />}
      </div>
    </div>
  )
}

function CatalogComposition({
  title,
  rows,
}: {
  title: string
  rows: Array<{ nombre: string; productos: number }>
}) {
  if (!rows.length) return null
  return (
    <Card>
      <h2 className="text-sm font-semibold text-navy">{title}</h2>
      <div className="mt-3 h-48">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={rows.slice(0, 8)} dataKey="productos" nameKey="nombre" innerRadius={42} outerRadius={67} paddingAngle={2}>
              {rows.slice(0, 8).map((item, index) => (
                <Cell key={item.nombre} fill={CATEGORICAL[index % CATEGORICAL.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(value) => formatNumber(Number(value))} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-2">
        {rows.slice(0, 8).map((item, index) => (
          <div key={item.nombre} className="flex min-w-0 items-center gap-2 text-[11px]">
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: CATEGORICAL[index % CATEGORICAL.length] }} />
            <span className="min-w-0 flex-1 truncate text-navy/65">{item.nombre}</span>
            <strong className="text-navy">{formatNumber(item.productos)}</strong>
          </div>
        ))}
      </div>
    </Card>
  )
}
