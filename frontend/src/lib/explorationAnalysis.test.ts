import { describe, expect, it } from 'vitest'
import { buildExplorationModel, explainExploration, explorationValue, explorationActions, type ExplorationMeasure } from './explorationAnalysis'
import type { MetricsResult } from './types'

function base(overrides: Partial<MetricsResult> = {}): MetricsResult {
  return {
    archivo: 'fixture.csv', moneda: 'CLP', advertencias: [], calidad_datos: 100, mapeo: {},
    periodo: { desde: null, hasta: null, meses_disponibles: [] },
    kpis: { ingresos_totales: { valor: 1000, variacion_pct: null }, gastos_totales: null, ganancia_neta: null, margen_utilidad_pct: null, flujo_caja: null, transacciones: 10, ticket_promedio: 100 },
    evolucion_mensual: [], agrupado_por_canal: null, proyeccion: null,
    indicadores_financieros: { disponible: false, nota: '', items: {} }, ...overrides,
  }
}
const measure = (overrides: Partial<ExplorationMeasure> = {}): ExplorationMeasure => ({ id: 'total', label: 'Total', value: 300, format: 'moneda', formula: 'Suma', series: [], dimensions: [], ...overrides })

describe('explorationActions', () => {
  it('keeps decisions brief and does not equate revenue with profit', () => {
    const actions = explorationActions(measure({ id: 'ingresos', dimensions: [{ name: 'Producto', groups: [{ name: 'A', value: 100 }, { name: 'B', value: -20 }] }] }), base())
    expect(actions.length).toBeLessThanOrEqual(3)
    expect(actions[0].evidence).toContain('100 CLP')
    expect(actions[0].action).toContain('no garantizan más utilidad')
    expect(actions[1].action).toContain('No elimines')
  })
  it('does not recommend cutting high costs automatically', () => {
    const actions = explorationActions(measure({ id: 'costo', dimensions: [{ name: 'Producto', groups: [{ name: 'A', value: 100 }] }] }), base())
    expect(actions[0].action).toContain('no demuestra ineficiencia')
  })
  it('only suggests inactivity checks from backend ID evidence', () => {
    const selected = measure({ id: 'ingresos' })
    expect(explorationActions(selected, base()).some((row) => /sin ventas/.test(row.title))).toBe(false)
    const metrics = base({ actividad_productos: { clave: 'id_producto', fecha_corte: '2026-06-30', meses_revisados: ['2026-04', '2026-05', '2026-06'], productos_revisados: 2, total_sin_ventas: 1, limite: 'Alcance observado', productos: [{ id: '001', nombre: 'Invierno', ultima_venta: '2026-02-01', meses_sin_venta_observada: 4, ingresos_historicos: 900 }] } })
    const action = explorationActions(selected, metrics)[0]
    expect(action.evidence).toContain('4 meses sin ventas positivas observadas')
    expect(action.action).toContain('estacionalidad')
    expect(action.action).toContain('No equivale a falta de demanda')
    expect(explorationActions(measure({ id: 'costo' }), metrics)[0].title).not.toMatch(/sin ventas/)
  })
})

describe('explainExploration', () => {
  it('compares consecutive full months with measured amounts', () => {
    const rows = explainExploration(measure({ series: [{ period: '2026-01', value: 100 }, { period: '2026-02', value: 150 }] }), 'UF')
    expect(rows[0].title).toContain('2026-01 y 2026-02')
    expect(rows[0].evidence).toContain('50 UF')
    expect(rows[0].evidence).toContain('50%')
  })
  it.each([
    [[{ period: '2026-01', value: 100 }, { period: '2026-03', value: 150 }]],
    [[{ period: '2026-01', value: 100 }, { period: '2026-02', value: 150, partial: true }]],
    [[{ period: '2026-01', value: null }, { period: '2026-02', value: 150 }]],
  ])('does not infer growth with gaps, partial months or unknown values', (series) => {
    expect(explainExploration(measure({ series }), 'CLP')[0].title).toBe('Comparación temporal no concluyente')
  })
  it('does not compare partially selected boundary months', () => {
    const selected = measure({ series: [{ period: '2026-01', value: 100 }, { period: '2026-02', value: 150 }] })
    expect(explainExploration(selected, 'CLP', undefined, '2026-01-15', '2026-02-28')[0].title).toContain('no concluyente')
    expect(explainExploration(selected, 'CLP', undefined, '2026-01-01', '2026-02-15')[0].title).toContain('no concluyente')
  })
  it('never emits percentages from zero or negative bases', () => {
    for (const value of [0, -100]) {
      const result = explainExploration(measure({ series: [{ period: '2026-01', value }, { period: '2026-02', value: 150 }] }), 'CLP')
      expect(result[0].evidence).toContain('No se calcula variación porcentual')
    }
  })
  it('uses the selected dimension and discloses truncated groups and negative values', () => {
    const result = explainExploration(measure({ dimensions: [
      { name: 'Sucursal', groups: [{ name: 'Centro', value: 900 }] },
      { name: 'Categoría', totalGroups: 20, groups: [{ name: 'Servicios', value: 300 }, { name: 'Reversas', value: -40 }] },
    ] }), 'CLP', 'Categoría')
    expect(result[1].evidence).toContain('Servicios')
    expect(result[1].evidence).not.toContain('Centro')
    expect(result[1].meaning).toContain('2 de 20')
    expect(result[1].meaning).toContain('valores negativos')
    expect(result[1].meaning).toContain('No demuestra causalidad')
  })
  it('decomposes movements only when both monthly grouped sums reconcile', () => {
    const selected = measure({ series: [{ period: '2026-01', value: 100 }, { period: '2026-02', value: 150 }], movement: { dimension: 'Sucursal', values: [
      { period: '2026-01', name: 'Centro', value: 100 }, { period: '2026-02', name: 'Centro', value: 80 }, { period: '2026-02', name: 'Sur', value: 70 },
    ] } })
    const result = explainExploration(selected, 'CLP')
    expect(result[1].title).toContain('Dónde se concentra el cambio')
    expect(result[1].evidence).toContain('Sur: +70 CLP')
    expect(result[1].evidence).toContain('Centro: -20 CLP')
    selected.movement!.values[0].value = 95
    expect(explainExploration(selected, 'CLP')).toHaveLength(1)
  })
})

describe('buildExplorationModel', () => {
  it('does not invent profit or liquidity from sales', () => {
    const result = buildExplorationModel(base())
    expect(result.measures.map((item) => item.id)).toEqual(['ingresos'])
    expect(result.cautions.join(' ')).toContain('liquidez')
  })
  it('keeps expenses semantic totals distinct from sales and taxes', () => {
    const result = buildExplorationModel(base({ analisis_generico: {
      registros: 10, columnas: 3, columnas_disponibles: [], celdas_informadas_pct: 90, subtipo: 'gastos',
      numericas: [{ columna: 'Total_gasto', etiqueta: 'Gastos totales', total: 2000, promedio: 200, mediana: 150, minimo: 5, maximo: 500, formato: 'moneda', valores_validos: 10 }],
      desgloses: [{ columna: 'Total_gasto', dimension: 'Centro_costo', operacion: 'total', formato: 'moneda', valores_totales: 2, valores: [{ nombre: 'Administración', valor: 2000, registros: 10 }] }],
    } }))
    expect(result.measures[0].label).toBe('Gastos totales')
    expect(result.measures[0].value).toBe(2000)
    expect(result.measures[0].dimensions[0].name).toBe('Centro costo')
    expect(result.cautions.join(' ')).toContain('Gasto, neto e IVA')
    expect(result.measures.some((item) => item.label === 'Ingresos')).toBe(false)
  })
  it('does not sum a percentage when only its mean is valid', () => {
    const result = buildExplorationModel(base({ analisis_generico: {
      registros: 2, columnas: 1, columnas_disponibles: [], celdas_informadas_pct: 100,
      numericas: [{ columna: 'meta_margen', total: null, promedio: 30, mediana: 30, minimo: 20, maximo: 40, formato: 'porcentaje', destacado: 'promedio' }],
    } }))
    expect(result.measures[0].value).toBe(30)
    expect(result.measures[0].formula).toMatch(/^Promedio/)
  })
  it('counts low stock as records instead of products', () => {
    const result = buildExplorationModel(base({ analisis_inventario: {
      registros: 100, productos: 20, stock_total: 1000, stock_minimo_total: 50, bajo_minimo: 25, cobertura_stock_pct: 95, sucursales: [], columna_actualizacion: null,
    } }))
    expect(result.measures[1].label).toBe('Registros bajo mínimo')
    expect(result.context).toContain('20 productos distintos')
    expect(result.cautions.join(' ')).toContain('no productos únicos')
  })
  it('makes retained duplicates and undated monetary coverage explicit', () => {
    const result = buildExplorationModel(base({ duplicados: { detectados: 5, conservados: 5, eliminados: 0 }, periodo: { desde: null, hasta: null, meses_disponibles: [], sin_fecha: { filas: 2, monto: 100, excluidas_por_filtro: false } } }))
    expect(result.cautions.join(' ')).toContain('5 duplicados conservados')
    expect(result.cautions.join(' ')).toContain('incluidos en el total global, pero no en la serie mensual')
  })
  it('reads join provenance with ratio coverage and does not invent missing-key count', () => {
    const result = buildExplorationModel(base({ analysis_provenance: { mode: 'join', left_sheet: 'Ventas', right_sheet: 'Productos', rows_before: 100, rows_after: 100, coverage: 0.9, filas_sin_correspondencia: 10 } }))
    expect(result.relations[0]).toMatchObject({ rows: 100, matched: 90, unmatched: 10, missing: null, coverage: 90 })
  })
  it('keeps numeric units explicit for UF and unavailable values', () => {
    expect(explorationValue(25.42, 'moneda', 'UF')).toBe('25,42 UF')
    expect(explorationValue(null, 'moneda', 'UF')).toBe('No disponible')
  })
  it('keeps collection groups on the collection base, not on total revenue', () => {
    const metrics = base({ analisis_negocio: {
      cobranza: {
        kpis: { registros: 5, registros_cobranza: 3, recaudacion_cobranza: 80, recaudacion_total: 100 },
        evolucion: [{ periodo: '2026-01', recaudacion_cobranza: 80, recaudacion_total: 100 }],
        equipos: [{ equipo: 'Legal', subgrupo: 'A', recaudacion_cobranza: 80, recaudacion_total: 100 }],
        agencias: [{ nombre: 'Banco', valor: 80 }], formas_pago: [], periodos_cotizados: [], descripciones_pago: [], notas: [],
      },
      calidad: { integridad_referencial: [], filas_inconsistentes_formula: 0 }, decisiones: [], alcance: { documentos_repetidos: 0, documentos_conflictivos: 0 },
    } } as unknown as Partial<MetricsResult>)
    const result = buildExplorationModel(metrics)
    expect(result.measures[0].value).toBe(80)
    expect(result.measures[1].value).toBe(100)
    expect(result.measures[0].dimensions.map((item) => item.name)).toContain('Agencia de pago')
    expect(result.measures[1].dimensions.map((item) => item.name)).not.toContain('Agencia de pago')
    expect(result.cautions.join(' ')).toContain('morosidad ni liquidez')
  })
  it('does not describe catalog reference costs as realized sales', () => {
    const result = buildExplorationModel(base({ analisis_productos: {
      productos: 2, cobertura_costo_pct: 50, costos: { promedio: 50 }, precios_lista: { promedio: 100 }, ranking_costos: [],
    } } as unknown as Partial<MetricsResult>))
    expect(result.subject).toContain('Catálogo')
    expect(result.measures[0].value).toBe(50)
    expect(result.cautions[0]).toContain('no es utilidad realizada')
  })
  it('uses campaign ratios provided by the engine without inferring return', () => {
    const result = buildExplorationModel(base({ analisis_campanas: {
      campanas: 3, impresiones: 1000, clics: 50, inversion: 500, ctr_pct: 5, cpc: 10, plataformas: [], estados: [],
      por_plataforma: [{ nombre: 'Buscador', campanas: 3, impresiones: 1000, clics: 50, inversion: 500, ctr_pct: 5, cpc: 10 }],
    } }))
    expect(result.measures[2].value).toBe(5)
    expect(result.measures[2].formula).toContain('no promedio simple')
    expect(result.cautions[0]).toContain('no se calcula ROAS')
  })
  it('does not replace an unavailable business profit with another KPI basis', () => {
    const metrics = base({ analisis_negocio: {
      estado_resultados: { ventas_observadas: 200, costo_venta_conocido: 50, utilidad_bruta: null, cobertura_costos_pct: 10 },
      evolucion: [], agrupaciones: {}, calidad: { integridad_referencial: [], filas_inconsistentes_formula: 0 }, decisiones: [], alcance: { filas_indicadores: 5, documentos_repetidos: 0, documentos_conflictivos: 0 },
    } } as unknown as Partial<MetricsResult>)
    metrics.kpis.ganancia_neta = { valor: 999, variacion_pct: null }
    expect(buildExplorationModel(metrics).measures.map((item) => item.id)).not.toContain('utilidad')
  })
})
