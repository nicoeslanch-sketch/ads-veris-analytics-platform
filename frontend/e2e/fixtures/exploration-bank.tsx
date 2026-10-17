import React from 'react'
import { createRoot } from 'react-dom/client'
import ExplorationChartBank from '../../src/components/ExplorationChartBank'
import { buildExplorationModel } from '../../src/lib/explorationAnalysis'
import type { MetricsResult, ProductPatterns, RelationalLedger } from '../../src/lib/types'
import demo from '../../src/demo/data/demo_metrics.json'
import '../../src/index.css'

const months = Array.from({ length: 24 }, (_, i) => `${2024 + Math.floor(i / 12)}-${String(i % 12 + 1).padStart(2, '0')}`)
const products = ['Regalo corporativo edición temporada con nombre extenso', 'Producto de uso permanente', 'Producto con devolución']
const patterns: ProductPatterns = { meses: months, anos_comparables: ['2024', '2025'], productos_revisados: 3, total_picos: 1, criterio: 'Dos años comparables', limite: 'Los ceros indican ausencia de ventas en el archivo observado.', series: products.map((nombre, i) => ({ id: '00' + i, nombre, valores: months.map(mes => ({ mes, ventas_netas: i === 2 ? -20 : mes.endsWith('12') ? 1000 : 20, ventas_positivas: i === 2 ? 0 : mes.endsWith('12') ? 1000 : 20 })) })), picos_recurrentes: [{ id: '000', nombre: products[0], mes: 12, evidencia: ['2024', '2025'].map(ano => ({ ano, mes: 12, ventas_positivas: 1000, participacion_pct: 82 })) }] }
const metrics = { ...demo, tipo_analisis: 'ventas', moneda: new URLSearchParams(location.search).get('currency') ?? 'CLP', patrones_productos: patterns, evolucion_mensual: months.map(mes => ({ mes, ingresos: 1000, gastos: 400, utilidad: 600, parcial: false })), actividad_productos: { clave: 'id_producto', fecha_corte: '2025-12-31', meses_revisados: months.slice(-3), productos_revisados: 3, total_sin_ventas: 1, limite: '', productos: [{ id: '003', nombre: 'Producto sin ventas recientes', ultima_venta: '2025-05-01', meses_sin_venta_observada: 7, ingresos_historicos: 100 }] }, top_productos: products.map((nombre, i) => ({ nombre, ingresos: (3 - i) * 1000, utilidad: (2 - i) * 500, cobertura_costos_pct: 100 })) } as unknown as MetricsResult
const ledger: RelationalLedger = { available: true, moneda: metrics.moneda, fuentes: [], relaciones: [], advertencias: [], patrones_productos: patterns, mensual: months.map(mes => ({ mes, ventas: 1000, costo: 400, utilidad: 600, unidades: 10 })), productos: products.map((nombre, i) => ({ nombre, ventas: (3 - i) * 1000, costo: 1000, utilidad: (2 - i) * 1000, unidades: 10 })), inventario_lento: [{ nombre: products[0], stock: 10, valor: 10000, dias_sin_venta: 120 }], kpis: { ventas_netas: 6000, costo_ventas_neto: 3000, utilidad_bruta: 3000, gastos_operacionales_netos: 1000, nominas: 1500, comisiones_cobro: 100, intereses_pagados: 200, resultado_antes_impuestos: 200, cuentas_por_cobrar: 500, cuentas_por_pagar: 300, inventario_valorizado: 10000 } }
createRoot(document.getElementById('root')!).render(<React.StrictMode><main className="mx-auto max-w-5xl p-4">
  {new URLSearchParams(location.search).get('scope') === 'ledger' ? <ExplorationChartBank ledger={ledger} /> : <ExplorationChartBank metrics={metrics} measure={buildExplorationModel(metrics).measures[0]} />}
</main></React.StrictMode>)
