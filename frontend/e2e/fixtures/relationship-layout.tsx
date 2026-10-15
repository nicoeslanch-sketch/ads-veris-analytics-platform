import React from 'react'
import { createRoot } from 'react-dom/client'
import RelationshipKpis from '../../src/components/relationships/RelationshipKpis'
import RelationshipCatalog from '../../src/components/relationships/RelationshipCatalog'
import RelationshipCharts from '../../src/components/relationships/RelationshipCharts'
import type { CatalogRelationship, RelationshipKpi } from '../../src/lib/types'
import '../../src/index.css'

const relation: CatalogRelationship = {
  id: 'synthetic', label: 'Gastos_Operacionales + Sucursales', left_sheet: 'Gastos_Operacionales',
  right_sheet: 'Sucursales', left_keys: ['ID_Sucursal'], right_keys: ['ID_Sucursal'], type: 'left',
  template: 'expenses_branches', purpose: 'test', coverage_left: 1, coverage_right: 1, overlap: 10,
  cardinality: 'muchos_a_uno', safe: true, recommended: true, source: 'automatic', currency_compatible: true, reason: null,
}
const kpis: RelationshipKpi[] = [
  { id: 'costo', label: 'Costo de venta estimado', value: 987654321012345, format: 'currency', available: true, help: null },
  { id: 'utilidad', label: 'Utilidad bruta estimada', value: -10000079, format: 'currency', available: true, help: null },
  { id: 'cobertura', label: 'Cobertura de costos', value: 65.8, format: 'percent', available: true, help: null },
]
createRoot(document.getElementById('root')!).render(<React.StrictMode>
  <main className="mx-auto grid max-w-5xl gap-4 p-4 md:grid-cols-[300px_minmax(0,1fr)]">
    <RelationshipCatalog relationships={[relation]} selectedId={relation.id} onSelect={() => {}} onCreate={() => {}} />
    <section aria-label="Indicadores de prueba" className="min-w-0 space-y-4"><RelationshipKpis kpis={kpis} currency="CLP" />
      <RelationshipCharts currency="CLP" charts={[{
        id: 'suppliers', kind: 'bar', title: 'Compras por proveedor', help: null, category_key: 'nombre',
        series: [{ key: 'compras', label: 'Compras', format: 'currency' }],
        data: Array.from({ length: 10 }, (_, i) => ({ nombre: `Proveedor con nombre extenso ${i + 1}`, compras: 26000000 - i * 1000000 })),
      }]} />
      <RelationshipCharts currency="CLP" charts={[{
        id: 'months', kind: 'bar', title: 'Compras por mes', help: null, category_key: 'mes',
        series: [{ key: 'compras', label: 'Compras', format: 'currency' }],
        data: Array.from({ length: 10 }, (_, i) => ({ mes: `2025-${String(i + 1).padStart(2, '0')}`, compras: 26000000 - i * 1000000 })),
      }]} />
    </section>
  </main>
</React.StrictMode>)
