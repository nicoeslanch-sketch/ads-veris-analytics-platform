import { principalPorParticipacionBruta } from './metrics'
import { soloMesesCompletos } from './partial'
import type { BusinessAnalysis, MetricsResult } from './types'

export type AlertSeverity = 'alta' | 'media' | 'baja'
export type AlertStatus = 'pendiente' | 'revisada' | 'resuelta'
export type AlertOrigin =
  | 'ventas'
  | 'costos'
  | 'productos'
  | 'pagos'
  | 'inventario'
  | 'relaciones'
  | 'calidad'

export interface AlertRules {
  caida_ingresos: { activa: boolean; umbral_pct: number }
  margen_bajo: { activa: boolean; umbral_pct: number }
  concentracion_producto: { activa: boolean; umbral_pct: number }
  concentracion_canal: { activa: boolean; umbral_pct: number }
  advertencias_motor: { activa: boolean }
}

export interface BusinessAlert {
  id: string
  sheet?: string
  severity: AlertSeverity
  origin: AlertOrigin
  title: string
  evidence: string
  impact: string
  action: string
  confidence: number
  impactAmount?: number
  target: {
    to: string
    label: string
    state?: Record<string, unknown>
  }
}

export const DEFAULT_ALERT_RULES: AlertRules = {
  caida_ingresos: { activa: true, umbral_pct: 10 },
  margen_bajo: { activa: true, umbral_pct: 10 },
  concentracion_producto: { activa: true, umbral_pct: 40 },
  concentracion_canal: { activa: true, umbral_pct: 50 },
  advertencias_motor: { activa: true },
}

export function alertRulesKey(userId: string | null): string {
  return `ads-veris-alert-rules:${userId ?? 'anon'}`
}

export function loadAlertRules(userId: string | null): AlertRules {
  try {
    const raw = localStorage.getItem(alertRulesKey(userId))
    if (!raw) return DEFAULT_ALERT_RULES
    return { ...DEFAULT_ALERT_RULES, ...(JSON.parse(raw) as AlertRules) }
  } catch {
    return DEFAULT_ALERT_RULES
  }
}

export function alertStatusKey(userId: string | null, datasetId: string | null): string {
  return `ads-veris-alert-status:${userId ?? 'anon'}:${datasetId ?? 'session'}`
}

export function loadAlertStatuses(
  userId: string | null,
  datasetId: string | null,
): Record<string, AlertStatus> {
  try {
    const raw = localStorage.getItem(alertStatusKey(userId, datasetId))
    return raw ? JSON.parse(raw) as Record<string, AlertStatus> : {}
  } catch {
    return {}
  }
}

export function saveAlertStatuses(
  userId: string | null,
  datasetId: string | null,
  statuses: Record<string, AlertStatus>,
) {
  try {
    localStorage.setItem(alertStatusKey(userId, datasetId), JSON.stringify(statuses))
  } catch {
    // En navegación privada el estado vive únicamente en memoria.
  }
  window.dispatchEvent(new CustomEvent('ads-veris-alerts-updated'))
}

function pct(value: number) {
  return `${value.toLocaleString('es-CL', { maximumFractionDigits: 1 })}%`
}

function money(value: number) {
  return value.toLocaleString('es-CL', {
    style: 'currency',
    currency: 'CLP',
    maximumFractionDigits: 0,
  })
}

function alertTarget(origin: AlertOrigin, activeSheet?: string) {
  if (origin === 'relaciones') {
    return {
      to: '/?mode=join',
      label: 'Abrir Relación manual',
      state: { analysisMode: 'join' },
    }
  }
  if (origin === 'ventas' || origin === 'productos' || origin === 'inventario') {
    return {
      to: '/explorar',
      label: 'Abrir análisis',
      state: { alertOrigin: origin, sheet: activeSheet },
    }
  }
  return {
    to: `/limpieza?revision=1${activeSheet ? `&sheet=${encodeURIComponent(activeSheet)}` : ''}`,
    label: 'Abrir registros',
    state: { alertOrigin: origin, sheet: activeSheet },
  }
}

function originFromText(text: string): AlertOrigin {
  const normalized = text.toLowerCase()
  if (normalized.includes('costo') || normalized.includes('margen')) return 'costos'
  if (normalized.includes('producto') || normalized.includes('sku')) return 'productos'
  if (normalized.includes('pago') || normalized.includes('cobran')) return 'pagos'
  if (normalized.includes('inventario') || normalized.includes('stock')) return 'inventario'
  if (normalized.includes('relaci') || normalized.includes('referencia')) return 'relaciones'
  if (normalized.includes('venta') || normalized.includes('ingreso')) return 'ventas'
  return 'calidad'
}

function qualityAlerts(analysis: BusinessAnalysis, activeSheet?: string): BusinessAlert[] {
  const alerts: BusinessAlert[] = []
  const add = (
    id: string,
    severity: AlertSeverity,
    origin: AlertOrigin,
    title: string,
    evidence: string,
    impact: string,
    action: string,
    confidence = analysis.confianza_pct / 100,
  ) => alerts.push({
    id,
    sheet: activeSheet,
    severity,
    origin,
    title,
    evidence,
    impact,
    action,
    confidence,
    target: alertTarget(origin, activeSheet),
  })

  if (analysis.alcance.documentos_repetidos > 0) {
    add(
      'business_documentos_repetidos',
      'alta',
      'ventas',
      'Resolver documentos repetidos',
      `${analysis.alcance.documentos_repetidos.toLocaleString('es-CL')} documento(s) comparten un identificador.`,
      'Las ventas certificables excluyen los conflictos hasta que se determine la versión válida.',
      'Revisa los IDs repetidos y conserva únicamente la versión respaldada por el documento fuente.',
    )
  }
  if (analysis.alcance.documentos_conflictivos > 0) {
    add(
      'business_documentos_conflictivos',
      'alta',
      'ventas',
      'Resolver documentos con información contradictoria',
      `${analysis.alcance.documentos_conflictivos.toLocaleString('es-CL')} documento(s) repiten ID con montos o fechas diferentes.`,
      'No es seguro incluir esas filas en indicadores certificados.',
      'Abre las filas afectadas y confirma la versión empresarial correcta.',
    )
  }
  const coverage = analysis.estado_resultados.cobertura_costos_certificable_pct
  if (coverage < 95) {
    add(
      'business_cobertura_costos',
      coverage < 80 ? 'alta' : 'media',
      'costos',
      'Completar la cobertura de costos',
      `${pct(coverage)} de las ventas certificables tiene un costo relacionable.`,
      'La utilidad y el margen representan solo la base con costo conocido.',
      'Relaciona el catálogo de costos vigente o corrige las claves sin correspondencia.',
    )
  }
  const negativeCosts = Number(analysis.calidad.costos.negativos ?? 0)
  if (negativeCosts > 0) {
    add(
      'business_costos_negativos',
      'alta',
      'costos',
      'Revisar costos negativos',
      `${negativeCosts.toLocaleString('es-CL')} costo(s) tienen valor negativo.`,
      'Pueden aumentar artificialmente la utilidad bruta.',
      'Confirma si son notas de crédito válidas o errores de origen.',
    )
  }
  if (analysis.calidad.filas_inconsistentes_formula > 0) {
    add(
      'business_formulas',
      'media',
      'calidad',
      'Revisar cálculos que no cuadran',
      `${analysis.calidad.filas_inconsistentes_formula.toLocaleString('es-CL')} fila(s) no cumplen su fórmula de control.`,
      'Monto, IVA, total, inventario o compra pueden no representar el documento fuente.',
      'Abre la evidencia y corrige el origen; ADS Veris no reemplaza esos valores silenciosamente.',
    )
  }
  if (analysis.calidad.referencias_problematicas > 0) {
    add(
      'business_referencias',
      'media',
      'relaciones',
      'Resolver referencias sin correspondencia',
      `${analysis.calidad.referencias_problematicas.toLocaleString('es-CL')} referencia(s) no encuentran su maestro.`,
      'Esas filas quedan fuera de costos, segmentaciones o enriquecimientos relacionados.',
      'Corrige las claves huérfanas o elige la conexión empresarial correcta.',
    )
  }
  if (analysis.operacion.documentos_sobrepagados > 0) {
    add(
      'business_sobrepagos',
      'alta',
      'pagos',
      'Revisar posibles sobrepagos',
      `${analysis.operacion.documentos_sobrepagados.toLocaleString('es-CL')} documento(s) tienen pagos superiores al total relacionado.`,
      'La cobranza aplicada y el saldo por cobrar pueden quedar distorsionados.',
      'Contrasta pagos, notas de crédito y documento de venta antes de conciliar.',
    )
  }
  return alerts
}

export function buildBusinessAlerts(
  metrics: MetricsResult,
  rules: AlertRules = DEFAULT_ALERT_RULES,
): BusinessAlert[] {
  if (metrics.moneda_mixta) return []
  const alerts: BusinessAlert[] = []
  const activeSheet = metrics.analysis_scope?.active_sheet
  const add = (alert: Omit<BusinessAlert, 'target'>) => {
    alerts.push({
      ...alert,
      sheet: alert.sheet ?? activeSheet,
      target: alertTarget(alert.origin, activeSheet),
    })
  }

  const complete = soloMesesCompletos(metrics.evolucion_mensual)
  if (rules.caida_ingresos.activa && complete.length >= 2) {
    const current = complete[complete.length - 1]
    const previous = complete[complete.length - 2]
    if (previous.ingresos > 0) {
      const variation = ((current.ingresos - previous.ingresos) / previous.ingresos) * 100
      if (variation <= -rules.caida_ingresos.umbral_pct) {
        add({
          id: 'caida_ingresos',
          severity: variation <= -25 ? 'alta' : 'media',
          origin: 'ventas',
          title: `Las ventas cayeron ${pct(Math.abs(variation))}`,
          evidence: `Pasaron de ${money(previous.ingresos)} a ${money(current.ingresos)} entre los dos últimos meses completos.`,
          impact: `La disminución nominal fue de ${money(previous.ingresos - current.ingresos)}.`,
          impactAmount: previous.ingresos - current.ingresos,
          action: 'Abre Explorar datos para identificar producto, canal o sucursal que explica la caída.',
          confidence: 0.95,
        })
      }
    }
  }

  const margin = metrics.kpis.margen_utilidad_pct?.valor
  if (rules.margen_bajo.activa && margin != null && margin < rules.margen_bajo.umbral_pct) {
    add({
      id: 'margen_bajo',
      severity: margin < 0 ? 'alta' : 'media',
      origin: 'costos',
      title: margin < 0 ? `Margen negativo: ${pct(margin)}` : `Margen bajo: ${pct(margin)}`,
      evidence: `El margen está bajo el umbral configurado de ${pct(rules.margen_bajo.umbral_pct)}.`,
      impact: 'Queda menos margen para cubrir gastos operativos, financieros e impuestos.',
      action: 'Revisa productos con alto volumen y bajo margen antes de cambiar precios o costos.',
      confidence: 0.9,
    })
  }

  const product = principalPorParticipacionBruta(metrics.top_productos ?? [])
  const productShare = product?.participacion_bruta_pct ?? product?.porcentaje
  if (
    rules.concentracion_producto.activa
    && product
    && productShare != null
    && productShare > rules.concentracion_producto.umbral_pct
  ) {
    add({
      id: 'concentracion_producto',
      severity: 'media',
      origin: 'productos',
      title: `Alta concentración en ${product.nombre}`,
      evidence: `Representa ${pct(productShare)} de las ventas brutas.`,
      impact: 'Una caída del producto tendría un efecto desproporcionado en los ingresos.',
      action: 'Compara margen, volumen y alternativas del portafolio.',
      confidence: 0.9,
    })
  }

  const channel = principalPorParticipacionBruta(metrics.ventas_por_canal ?? [])
  const channelShare = channel?.participacion_bruta_pct ?? channel?.porcentaje
  if (
    rules.concentracion_canal.activa
    && channel
    && (metrics.ventas_por_canal?.length ?? 0) >= 2
    && channelShare != null
    && channelShare > rules.concentracion_canal.umbral_pct
  ) {
    add({
      id: 'concentracion_canal',
      severity: 'baja',
      origin: 'ventas',
      title: `Concentración en ${channel.nombre}`,
      evidence: `El canal o sucursal aporta ${pct(channelShare)} de las ventas brutas.`,
      impact: 'La operación depende en gran medida de una sola fuente comercial.',
      action: 'Compara crecimiento y margen de los canales secundarios.',
      confidence: 0.9,
    })
  }

  if (rules.advertencias_motor.activa) {
    metrics.advertencias.forEach((warning) => {
      const origin = originFromText(warning)
      add({
        id: `motor_${origin}_${warning.normalize('NFKD').replace(/\W+/g, '_').slice(0, 70)}`,
        severity: 'baja',
        origin,
        title: 'Advertencia del motor de datos',
        evidence: warning,
        impact: 'Puede limitar la cobertura o comparabilidad de uno o más indicadores.',
        action: 'Abre los registros afectados y valida el dato contra su fuente.',
        confidence: 0.8,
      })
    })
  }

  if (metrics.analisis_negocio) {
    alerts.push(...qualityAlerts(metrics.analisis_negocio, activeSheet))
    metrics.analisis_negocio.decisiones.forEach((decision) => {
      const origin = originFromText(`${decision.titulo} ${decision.evidencia}`)
      add({
        id: `decision_${decision.titulo.normalize('NFKD').replace(/\W+/g, '_').slice(0, 70)}`,
        severity: decision.severidad,
        origin,
        title: decision.titulo,
        evidence: decision.evidencia,
        impact: 'Este hallazgo puede afectar la interpretación ejecutiva del periodo.',
        action: decision.accion,
        confidence: decision.confianza,
      })
    })
  }

  const deduplicated = [...new Map(alerts.map((alert) => [alert.id, alert])).values()]
  const severityOrder: Record<AlertSeverity, number> = { alta: 0, media: 1, baja: 2 }
  return deduplicated.sort((left, right) => (
    severityOrder[left.severity] - severityOrder[right.severity]
    || (right.impactAmount ?? 0) - (left.impactAmount ?? 0)
    || left.title.localeCompare(right.title, 'es')
  ))
}
