import Card from './ui/Card'
import { formatCLP, formatNumber } from '../lib/format'
import { AXIS_INK, CHART, GRID_STROKE, formatCLPCompact, truncateLabel } from '../lib/charts'
import type { MetricsResult } from '../lib/types'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
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

export default function ProductCatalogSummary({ analysis }: { analysis: ProductAnalysis }) {
  const totals = analysis.totales_catalogo_unitario
  const costReference = analysis.referencia_tipo === 'costo_total_unitario'
  const referenceLabel = costReference ? 'Costo total unitario' : 'Precio lista'
  const differenceLabel = costReference ? 'Componente adicional' : 'Margen potencial'
  const cards = [
    ['Productos', formatNumber(analysis.productos)],
    ['Costo promedio', money(analysis.costos.promedio)],
    ['Costo mediano', money(analysis.costos.mediana)],
    ['Rango de costo', `${money(analysis.costos.minimo)} - ${money(analysis.costos.maximo)}`],
    [`${referenceLabel} promedio`, money(analysis.precios_lista.promedio)],
    [`${differenceLabel} promedio`, pct(analysis.margen_potencial.promedio)],
    ['Cobertura de costos', `${formatNumber(analysis.cobertura_costo_pct)}%`],
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
  const comparison = analysis.ranking_costos.slice(0, 10).map((item) => ({
    ...item,
    etiqueta: truncateLabel(item.producto, 22),
  }))
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(([label, value]) => (
          <Card key={label} className="!p-4">
            <p className="text-xs text-navy/50">{label}</p>
            <p className="mt-1 text-lg font-bold text-navy">{value}</p>
          </Card>
        ))}
      </div>
      <p className="rounded-xl border border-teal/20 bg-teal/5 px-4 py-3 text-xs leading-relaxed text-navy/65">
        Los totales de catálogo suponen una unidad de cada producto. No representan inventario
        ni gasto real; para valorizar existencias se necesita relacionar la cantidad en stock.
      </p>
      {comparison.length > 0 && (
        <Card>
          <h2 className="text-sm font-semibold text-navy">Costo unitario vs. {referenceLabel.toLowerCase()}</h2>
          <p className="mt-1 text-xs text-navy/55">Los 10 productos con mayor costo unitario.</p>
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
        <Card>
          <h2 className="text-sm font-semibold text-navy">Ranking por costo unitario</h2>
          <div className="mt-3 space-y-2">
            {analysis.ranking_costos.slice(0, 10).map((item, index) => (
              <div key={`${item.producto}-${index}`} className="flex items-center gap-3 text-xs">
                <span className="w-5 text-navy/40">{index + 1}</span>
                <span className="min-w-0 flex-1 truncate font-semibold text-navy">{item.producto}</span>
                <span className="text-navy/65">{money(item.costo)}</span>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <h2 className="text-sm font-semibold text-navy">Categorias</h2>
          <div className="mt-3 space-y-2">
            {analysis.categorias.map((item) => (
              <div key={item.nombre} className="flex justify-between gap-3 text-xs">
                <span className="truncate text-navy/70">{item.nombre}</span>
                <strong className="text-navy">{formatNumber(item.productos)}</strong>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <h2 className="text-sm font-semibold text-navy">Marcas</h2>
          <div className="mt-3 space-y-2">
            {analysis.marcas.map((item) => (
              <div key={item.nombre} className="flex justify-between gap-3 text-xs">
                <span className="truncate text-navy/70">{item.nombre}</span>
                <strong className="text-navy">{formatNumber(item.productos)}</strong>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
