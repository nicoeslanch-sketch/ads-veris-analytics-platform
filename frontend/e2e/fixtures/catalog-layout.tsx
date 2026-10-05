import React from 'react'
import { createRoot } from 'react-dom/client'
import ProductCatalogSummary from '../../src/components/ProductCatalogSummary'
import { setActiveCurrency } from '../../src/lib/format'
import type { MetricsResult } from '../../src/lib/types'
import '../../src/index.css'

setActiveCurrency(new URLSearchParams(location.search).get('currency') ?? 'CLP')
const analysis: NonNullable<MetricsResult['analisis_productos']> = {
  productos: 4, registros: 5, columna_producto: 'Producto', estado_unidad: 'registros', sin_estado: 2,
  costos: {promedio: 220, mediana: 200, minimo: 100, maximo: 987654321012345},
  precios_lista: {promedio: 440, mediana: 400, minimo: 200, maximo: 800},
  margen_potencial: {promedio: 50, mediana: 50, minimo: 50, maximo: 50},
  totales_catalogo_unitario: {costo: 1100, precio_lista: 2200, utilidad_potencial: 1100, productos_con_comparacion: 5},
  cobertura_costo_pct: 100, activos: 2, inactivos: 1,
  ranking_costos: [{producto: 'Producto de prueba con nombre largo', costo: 100, precio_lista: 200, margen_potencial_pct: 50}],
  categorias: [{nombre: 'Hogar', productos: 3}, {nombre: 'Oficina', productos: 2}], marcas: [],
}
createRoot(document.getElementById('root')!).render(<React.StrictMode>
  <main className="mx-auto max-w-6xl p-4"><ProductCatalogSummary analysis={analysis} variant="explore" /></main>
</React.StrictMode>)
