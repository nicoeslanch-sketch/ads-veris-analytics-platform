import { describe, expect, it } from 'vitest'
import { buildBusinessAlerts, DEFAULT_ALERT_RULES } from './businessAlerts'
import type { BusinessAnalysis, MetricsResult } from './types'

function metricsFixture(): MetricsResult {
  const analysis = {
    estado_certificacion: 'blocked',
    confianza_pct: 72,
    alcance: {
      documentos_repetidos: 4,
      documentos_conflictivos: 2,
    },
    estado_resultados: {
      cobertura_costos_certificable_pct: 82,
    },
    operacion: {
      documentos_sobrepagados: 1,
    },
    calidad: {
      costos: { negativos: 3 },
      filas_inconsistentes_formula: 5,
      referencias_problematicas: 8,
    },
    decisiones: [
      {
        severidad: 'alta',
        titulo: 'Revisar liquidez',
        evidencia: 'La cobranza no cubre todos los documentos.',
        accion: 'Reconciliar pagos.',
        confianza: 0.88,
      },
    ],
  } as unknown as BusinessAnalysis

  return {
    archivo: 'empresa.xlsx',
    calidad_datos: 80,
    moneda: 'CLP',
    mapeo: {},
    agrupado_por_canal: null,
    periodo: { desde: null, hasta: null, meses_disponibles: ['2026-01', '2026-02'] },
    kpis: {
      ingresos_totales: { valor: 700, variacion_pct: -30 },
      transacciones: 2,
      ticket_promedio: 350,
      gastos_totales: { valor: 900, variacion_pct: null },
      ganancia_neta: { valor: -200, variacion_pct: null },
      margen_utilidad_pct: { valor: -10, variacion_puntos: null },
      flujo_caja: null,
    },
    evolucion_mensual: [
      { mes: '2026-01', ingresos: 1000 },
      { mes: '2026-02', ingresos: 700 },
    ],
    proyeccion: null,
    indicadores_financieros: { disponible: false, nota: '', items: {} },
    advertencias: ['Una referencia de producto no tiene correspondencia.'],
    analisis_negocio: analysis,
  }
}

describe('alertas empresariales', () => {
  it('prioriza impacto alto y conserva evidencia, acción y navegación', () => {
    const alerts = buildBusinessAlerts(metricsFixture(), DEFAULT_ALERT_RULES)

    expect(alerts[0].severity).toBe('alta')
    expect(alerts.some((alert) => alert.id === 'business_cobertura_costos')).toBe(true)
    expect(alerts.some((alert) => alert.id === 'business_referencias')).toBe(true)
    expect(alerts.every((alert) => alert.evidence && alert.impact && alert.action)).toBe(true)
    expect(alerts.every((alert) => alert.target.to.startsWith('/'))).toBe(true)
  })

  it('no calcula alertas monetarias cuando las monedas son incompatibles', () => {
    const metrics = { ...metricsFixture(), moneda_mixta: true }
    expect(buildBusinessAlerts(metrics, DEFAULT_ALERT_RULES)).toEqual([])
  })
})
