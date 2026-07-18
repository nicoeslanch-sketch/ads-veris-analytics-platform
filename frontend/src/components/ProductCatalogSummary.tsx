import Card from './ui/Card'
import { formatCLP, formatNumber } from '../lib/format'
import type { MetricsResult } from '../lib/types'

type ProductAnalysis = NonNullable<MetricsResult['analisis_productos']>

function money(value: number | null) {
  return value == null ? '\u2014' : formatCLP(value)
}

function pct(value: number | null) {
  return value == null ? '\u2014' : `${formatNumber(value)}%`
}

export default function ProductCatalogSummary({ analysis }: { analysis: ProductAnalysis }) {
  const cards = [
    ['Productos', formatNumber(analysis.productos)],
    ['Costo promedio', money(analysis.costos.promedio)],
    ['Costo mediano', money(analysis.costos.mediana)],
    ['Rango de costo', `${money(analysis.costos.minimo)} - ${money(analysis.costos.maximo)}`],
    ['Precio lista promedio', money(analysis.precios_lista.promedio)],
    ['Margen potencial promedio', pct(analysis.margen_potencial.promedio)],
    ['Cobertura de costos', `${formatNumber(analysis.cobertura_costo_pct)}%`],
    ['Estado', `${formatNumber(analysis.activos ?? 0)} activos - ${formatNumber(analysis.inactivos ?? 0)} inactivos`],
  ]
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
