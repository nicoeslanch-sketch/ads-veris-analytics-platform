/**
 * Alertas — sistema de aviso temprano (SPEC §7 — Fase 5, MVP).
 *
 * Evalúa reglas configurables sobre las métricas del dataset de la sesión:
 * caída de ingresos m/m, margen bajo, concentración de producto y de canal,
 * más las advertencias del motor de datos. Cada alerta responde: qué pasó,
 * severidad, área afectada y recomendación. Panel derecho: resumen por
 * severidad y por área. Las reglas se guardan en el navegador (localStorage).
 */

import { useEffect, useMemo, useState } from 'react'
import {
  ArrowDownRight,
  Bell,
  BellRing,
  CheckCircle2,
  Loader2,
  Package,
  Percent,
  Settings2,
  Store,
  TriangleAlert,
  type LucideIcon,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import EmptyState from '../components/ui/EmptyState'
import Toggle from '../components/ui/Toggle'
import { useAuth } from '../auth/AuthContext'
import { useSessionMetrics } from '../data/useSessionMetrics'
import { formatCLP, formatNumber } from '../lib/format'
import { formatMonthShort } from '../lib/charts'
import type { MetricsResult } from '../lib/types'

// ── Reglas configurables ──────────────────────────────────────────────────────

interface AlertRules {
  caida_ingresos: { activa: boolean; umbral_pct: number }
  margen_bajo: { activa: boolean; umbral_pct: number }
  concentracion_producto: { activa: boolean; umbral_pct: number }
  concentracion_canal: { activa: boolean; umbral_pct: number }
  advertencias_motor: { activa: boolean }
}

const DEFAULT_RULES: AlertRules = {
  caida_ingresos: { activa: true, umbral_pct: 10 },
  margen_bajo: { activa: true, umbral_pct: 10 },
  concentracion_producto: { activa: true, umbral_pct: 40 },
  concentracion_canal: { activa: true, umbral_pct: 50 },
  advertencias_motor: { activa: true },
}

/** Key por usuario: en un computador compartido, las reglas de una cuenta
 * no deben heredarse a la siguiente que inicie sesión. */
function rulesKey(userId: string | null): string {
  return `ads-veris-alert-rules:${userId ?? 'anon'}`
}

function loadRules(userId: string | null): AlertRules {
  try {
    const raw = localStorage.getItem(rulesKey(userId))
    if (!raw) return DEFAULT_RULES
    return { ...DEFAULT_RULES, ...(JSON.parse(raw) as AlertRules) }
  } catch {
    return DEFAULT_RULES
  }
}

// ── Evaluación de alertas ─────────────────────────────────────────────────────

type Severity = 'critica' | 'media' | 'baja'

interface Alert {
  id: string
  severity: Severity
  area: string
  icon: LucideIcon
  titulo: string
  detalle: string
  recomendacion: string
}

const SEVERITY_META: Record<Severity, { label: string; tone: 'coral' | 'gold' | 'teal'; border: string }> = {
  critica: { label: 'Crítica', tone: 'coral', border: 'border-l-coral' },
  media: { label: 'Media', tone: 'gold', border: 'border-l-gold' },
  baja: { label: 'Baja', tone: 'teal', border: 'border-l-teal' },
}

function formatPct(value: number): string {
  return `${value.toLocaleString('es-CL', { maximumFractionDigits: 1 })}%`
}

function computeAlerts(m: MetricsResult, rules: AlertRules): Alert[] {
  const alerts: Alert[] = []
  const evo = m.evolucion_mensual

  // Caída de ingresos mes a mes
  if (rules.caida_ingresos.activa && evo.length >= 2) {
    const last = evo[evo.length - 1]
    const prev = evo[evo.length - 2]
    if (prev.ingresos > 0) {
      const pct = ((last.ingresos - prev.ingresos) / prev.ingresos) * 100
      if (pct <= -rules.caida_ingresos.umbral_pct) {
        alerts.push({
          id: 'caida_ingresos',
          severity: pct <= -25 ? 'critica' : 'media',
          area: 'Ventas',
          icon: ArrowDownRight,
          titulo: `Tus ingresos cayeron ${formatPct(Math.abs(pct))} en ${formatMonthShort(last.mes)}`,
          detalle: `Pasaron de ${formatCLP(prev.ingresos)} a ${formatCLP(last.ingresos)} (regla: avisar sobre ${formatPct(rules.caida_ingresos.umbral_pct)}).`,
          recomendacion:
            'Revisa qué productos o canales explican la caída en Explorar datos y reactiva promociones donde más pesa.',
        })
      }
    }
  }

  // Margen de utilidad bajo
  const margen = m.kpis.margen_utilidad_pct?.valor
  if (rules.margen_bajo.activa && margen != null && margen < rules.margen_bajo.umbral_pct) {
    alerts.push({
      id: 'margen_bajo',
      severity: margen < 0 ? 'critica' : 'media',
      area: 'Rentabilidad',
      icon: Percent,
      titulo:
        margen < 0
          ? `Margen negativo: ${formatPct(margen)}`
          : `Margen de utilidad bajo: ${formatPct(margen)}`,
      detalle: `El margen del periodo está bajo tu umbral de ${formatPct(rules.margen_bajo.umbral_pct)}.`,
      recomendacion:
        'Identifica la categoría menos rentable en Explorar datos y revisa precios o costos de esa línea.',
    })
  }

  // Concentración del producto top
  const topProducto = m.top_productos?.[0]
  if (
    rules.concentracion_producto.activa &&
    topProducto &&
    topProducto.porcentaje > rules.concentracion_producto.umbral_pct
  ) {
    alerts.push({
      id: 'concentracion_producto',
      severity: 'media',
      area: 'Productos',
      icon: Package,
      titulo: `"${topProducto.nombre}" concentra el ${formatPct(topProducto.porcentaje)} de tus ingresos`,
      detalle: `Supera tu umbral de concentración del ${formatPct(rules.concentracion_producto.umbral_pct)}.`,
      recomendacion:
        'Alta dependencia de un producto: potencia productos secundarios para reducir riesgo.',
    })
  }

  // Concentración de canal / sucursal
  const canal = m.ventas_por_canal?.[0]
  if (
    rules.concentracion_canal.activa &&
    canal &&
    (m.ventas_por_canal?.length ?? 0) >= 2 &&
    canal.porcentaje > rules.concentracion_canal.umbral_pct
  ) {
    alerts.push({
      id: 'concentracion_canal',
      severity: 'baja',
      area: 'Canales',
      icon: Store,
      titulo: `"${canal.nombre}" genera el ${formatPct(canal.porcentaje)} de tus ventas`,
      detalle: `Supera tu umbral del ${formatPct(rules.concentracion_canal.umbral_pct)}: gran parte del negocio depende de un canal.`,
      recomendacion: 'Fortalece los canales secundarios para no depender de uno solo.',
    })
  }

  // Advertencias del motor de datos
  if (rules.advertencias_motor.activa) {
    m.advertencias.forEach((advertencia, i) => {
      alerts.push({
        id: `advertencia_${i}`,
        severity: 'baja',
        area: 'Calidad de datos',
        icon: TriangleAlert,
        titulo: 'Advertencia del motor de datos',
        detalle: advertencia,
        recomendacion: 'Revisa el archivo original o vuelve a ejecutar la limpieza.',
      })
    })
  }

  const order: Severity[] = ['critica', 'media', 'baja']
  return alerts.sort((a, b) => order.indexOf(a.severity) - order.indexOf(b.severity))
}

// ── Componente ────────────────────────────────────────────────────────────────

export default function Alertas() {
  const { user } = useAuth()
  const userId = user?.id ?? null
  const { ready, metrics, loading, error } = useSessionMetrics()
  const [rules, setRules] = useState<AlertRules>(() => loadRules(userId))
  const [resolved, setResolved] = useState<string[]>([])

  // Si cambia la cuenta en el mismo navegador, cargar las reglas de ESA cuenta
  useEffect(() => {
    setRules(loadRules(userId))
  }, [userId])

  useEffect(() => {
    try {
      localStorage.setItem(rulesKey(userId), JSON.stringify(rules))
    } catch {
      // sin localStorage (modo privado): las reglas viven solo en la sesión
    }
  }, [rules, userId])

  const allAlerts = useMemo(
    () => (metrics ? computeAlerts(metrics, rules) : []),
    [metrics, rules],
  )
  const active = allAlerts.filter((a) => !resolved.includes(a.id))
  const resolvedAlerts = allAlerts.filter((a) => resolved.includes(a.id))

  const bySeverity = (sev: Severity) => active.filter((a) => a.severity === sev).length
  const areas = [...new Set(active.map((a) => a.area))]

  if (!ready) {
    return (
      <>
        <PageHeader
          title="Alertas"
          subtitle="Tu sistema de aviso temprano: las reglas se evalúan con tus datos cada vez que abres esta página."
        />
        <EmptyState
          icon={Bell}
          title="Sin alertas por ahora"
          description="Cuando cargues datos podrás definir reglas (ej.: avisar si las ventas bajan más de 10%) y recibir alertas con severidad, área afectada y recomendación."
          ctaLabel="Cargar mis datos"
          ctaTo="/estandarizacion"
        />
      </>
    )
  }

  if (loading) {
    return (
      <>
        <PageHeader title="Alertas" subtitle="Evaluando las reglas sobre tus datos…" />
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-teal" />
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Alertas"
        subtitle="Tu sistema de aviso temprano: las reglas se evalúan con tus datos cada vez que abres esta página."
      />

      {error && (
        <Card className="mb-6 border-coral/40 bg-coral/5">
          <p className="text-sm text-coral">{error}</p>
        </Card>
      )}

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-6">
          {/* Alertas activas */}
          <div>
            <div className="flex items-center gap-2">
              <BellRing className="h-5 w-5 text-coral" />
              <h2 className="text-lg font-semibold text-navy">
                Alertas activas ({active.length})
              </h2>
            </div>
            {active.length === 0 ? (
              <Card className="mt-4 border-green/25 bg-green/5">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="h-6 w-6 text-green" />
                  <div>
                    <p className="text-sm font-semibold text-navy">Todo en orden</p>
                    <p className="text-xs text-navy/60">
                      Ninguna regla activa se disparó con los datos del periodo.
                    </p>
                  </div>
                </div>
              </Card>
            ) : (
              <div className="mt-4 flex flex-col gap-4">
                {active.map((alert) => {
                  const meta = SEVERITY_META[alert.severity]
                  return (
                    <Card key={alert.id} className={`border-l-4 ${meta.border}`}>
                      <div className="flex flex-col items-start gap-3 sm:flex-row sm:justify-between">
                        <div className="flex items-start gap-3">
                          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-navy/5">
                            <alert.icon className="h-4.5 w-4.5 text-navy/70" />
                          </div>
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <h3 className="text-sm font-semibold text-navy">{alert.titulo}</h3>
                              <Badge tone={meta.tone}>{meta.label}</Badge>
                              <span className="text-xs text-navy/45">{alert.area}</span>
                            </div>
                            <p className="mt-1 text-xs text-navy/60">{alert.detalle}</p>
                            <p className="mt-2 text-xs leading-relaxed text-navy/75">
                              <span className="font-semibold text-teal">Recomendación: </span>
                              {alert.recomendacion}
                            </p>
                          </div>
                        </div>
                        <button
                          onClick={() => setResolved((prev) => [...prev, alert.id])}
                          className="w-full shrink-0 rounded-lg border border-navy/20 px-3 py-1.5 text-xs font-medium text-navy/70 transition-colors hover:bg-navy/5 sm:w-auto"
                        >
                          Marcar revisada
                        </button>
                      </div>
                    </Card>
                  )
                })}
              </div>
            )}
          </div>

          {/* Revisadas en la sesión */}
          {resolvedAlerts.length > 0 && (
            <div>
              <h2 className="text-lg font-semibold text-navy">
                Revisadas en esta sesión ({resolvedAlerts.length})
              </h2>
              <div className="mt-3 flex flex-col gap-2">
                {resolvedAlerts.map((alert) => (
                  <div
                    key={alert.id}
                    className="flex items-center justify-between rounded-xl border border-navy/10 bg-white px-4 py-2.5"
                  >
                    <p className="text-sm text-navy/50 line-through">{alert.titulo}</p>
                    <button
                      onClick={() => setResolved((prev) => prev.filter((id) => id !== alert.id))}
                      className="text-xs font-medium text-teal hover:underline"
                    >
                      Reactivar
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Reglas de alerta */}
          <Card>
            <div className="flex items-center gap-2">
              <Settings2 className="h-4.5 w-4.5 text-teal" />
              <h2 className="text-base font-semibold text-navy">Reglas de alerta</h2>
            </div>
            <p className="mt-0.5 text-sm text-navy/60">
              Define cuándo quieres que la plataforma te avise. Se guardan en este navegador.
            </p>
            <div className="mt-4 divide-y divide-navy/5">
              <RuleRow
                label="Avisar si los ingresos caen más de"
                suffix="% vs el mes anterior"
                value={rules.caida_ingresos}
                onChange={(v) => setRules((r) => ({ ...r, caida_ingresos: v }))}
              />
              <RuleRow
                label="Avisar si el margen de utilidad baja de"
                suffix="%"
                value={rules.margen_bajo}
                onChange={(v) => setRules((r) => ({ ...r, margen_bajo: v }))}
              />
              <RuleRow
                label="Avisar si un producto supera el"
                suffix="% de los ingresos"
                value={rules.concentracion_producto}
                onChange={(v) => setRules((r) => ({ ...r, concentracion_producto: v }))}
              />
              <RuleRow
                label="Avisar si un canal/sucursal supera el"
                suffix="% de las ventas"
                value={rules.concentracion_canal}
                onChange={(v) => setRules((r) => ({ ...r, concentracion_canal: v }))}
              />
              <div className="flex items-center justify-between py-3">
                <p className="text-sm text-navy/75">Incluir advertencias del motor de datos</p>
                <Toggle
                  checked={rules.advertencias_motor.activa}
                  label="Incluir advertencias del motor de datos"
                  onChange={(checked) =>
                    setRules((r) => ({ ...r, advertencias_motor: { activa: checked } }))
                  }
                />
              </div>
            </div>
          </Card>
        </div>

        {/* Panel derecho: resumen */}
        <div className="flex flex-col gap-6">
          <Card>
            <h2 className="text-base font-semibold text-navy">Resumen por severidad</h2>
            <div className="mt-4 grid grid-cols-3 gap-3 text-center">
              {(['critica', 'media', 'baja'] as Severity[]).map((sev) => {
                const meta = SEVERITY_META[sev]
                const count = bySeverity(sev)
                return (
                  <div key={sev} className="rounded-xl bg-navy/[0.03] px-2 py-3">
                    <p
                      className={`text-2xl font-bold ${
                        count > 0
                          ? sev === 'critica'
                            ? 'text-coral'
                            : sev === 'media'
                              ? 'text-gold'
                              : 'text-teal'
                          : 'text-navy/30'
                      }`}
                    >
                      {count}
                    </p>
                    <p className="mt-0.5 text-xs font-medium text-navy/60">{meta.label}</p>
                  </div>
                )
              })}
            </div>
          </Card>

          <Card>
            <h2 className="text-base font-semibold text-navy">Por área</h2>
            {areas.length === 0 ? (
              <p className="mt-3 text-sm text-navy/50">Sin áreas afectadas.</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {areas.map((area) => (
                  <li
                    key={area}
                    className="flex items-center justify-between rounded-lg bg-navy/[0.03] px-3 py-2 text-sm"
                  >
                    <span className="text-navy/75">{area}</span>
                    <span className="font-semibold text-navy">
                      {formatNumber(active.filter((a) => a.area === area).length)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="border-teal/25 bg-teal/5">
            <p className="text-xs leading-relaxed text-navy/60">
              Las alertas se evalúan sobre el dataset de la sesión cada vez que entras.
              La vigilancia continua (correo/notificaciones) llega con los Conectores.
            </p>
          </Card>
        </div>
      </div>
    </>
  )
}

// ── Sub-componentes ───────────────────────────────────────────────────────────

function RuleRow({
  label,
  suffix,
  value,
  onChange,
}: {
  label: string
  suffix: string
  value: { activa: boolean; umbral_pct: number }
  onChange: (v: { activa: boolean; umbral_pct: number }) => void
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 py-3">
      <p className="text-sm text-navy/75">
        {label}{' '}
        <input
          type="number"
          min={1}
          max={95}
          value={value.umbral_pct}
          onChange={(e) =>
            onChange({ ...value, umbral_pct: Math.max(1, Math.min(95, Number(e.target.value) || 0)) })
          }
          className="mx-1 w-16 rounded-lg border border-navy/20 bg-white px-2 py-1 text-sm text-navy outline-none focus:border-teal"
        />{' '}
        {suffix}
      </p>
      <Toggle checked={value.activa} label={label} onChange={(checked) => onChange({ ...value, activa: checked })} />
    </div>
  )
}
