import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Bell,
  BellRing,
  CheckCircle2,
  CircleDollarSign,
  ExternalLink,
  Link2,
  Loader2,
  Package,
  Receipt,
  Settings2,
  ShoppingCart,
  TriangleAlert,
  type LucideIcon,
} from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import PageHeader from '../components/ui/PageHeader'
import Toggle from '../components/ui/Toggle'
import { useDataset } from '../data/DatasetContext'
import { useSessionMetrics } from '../data/useSessionMetrics'
import {
  alertRulesKey,
  buildBusinessAlerts,
  loadAlertRules,
  loadAlertStatuses,
  saveAlertStatuses,
  type AlertOrigin,
  type AlertRules,
  type AlertSeverity,
  type AlertStatus,
} from '../lib/businessAlerts'

const SEVERITY: Record<AlertSeverity, { label: string; border: string; pill: string }> = {
  alta: { label: 'Alta', border: 'border-l-coral', pill: 'bg-coral/10 text-coral' },
  media: { label: 'Media', border: 'border-l-gold', pill: 'bg-gold/15 text-amber-700' },
  baja: { label: 'Baja', border: 'border-l-teal', pill: 'bg-teal/10 text-teal' },
}

const ORIGIN: Record<AlertOrigin, { label: string; icon: LucideIcon }> = {
  ventas: { label: 'Ventas', icon: ShoppingCart },
  costos: { label: 'Costos', icon: CircleDollarSign },
  productos: { label: 'Productos', icon: Package },
  pagos: { label: 'Pagos', icon: Receipt },
  inventario: { label: 'Inventario', icon: Package },
  relaciones: { label: 'Relaciones', icon: Link2 },
  calidad: { label: 'Calidad', icon: TriangleAlert },
}

const STATUS_LABEL: Record<AlertStatus, string> = {
  pendiente: 'Pendiente',
  revisada: 'Revisada',
  resuelta: 'Resuelta',
}

export default function Alertas() {
  const { user } = useAuth()
  const userId = user?.id ?? null
  const { datasetId, uploadedAt } = useDataset()
  const { ready, metrics, loading, error } = useSessionMetrics()
  const [params] = useSearchParams()
  const requestedOrigin = params.get('origin') as AlertOrigin | null
  const requestedSheet = params.get('sheet')
  const [rules, setRules] = useState<AlertRules>(() => loadAlertRules(userId))
  const [statuses, setStatuses] = useState<Record<string, AlertStatus>>(
    () => loadAlertStatuses(userId, datasetId),
  )
  const [severity, setSeverity] = useState<AlertSeverity | 'todas'>('todas')
  const [status, setStatus] = useState<AlertStatus | 'todas'>('pendiente')
  const [origin, setOrigin] = useState<AlertOrigin | 'todos'>(
    requestedOrigin && requestedOrigin in ORIGIN ? requestedOrigin : 'todos',
  )

  useEffect(() => {
    setRules(loadAlertRules(userId))
  }, [userId])

  useEffect(() => {
    setStatuses(loadAlertStatuses(userId, datasetId))
  }, [datasetId, uploadedAt, userId])

  useEffect(() => {
    try {
      localStorage.setItem(alertRulesKey(userId), JSON.stringify(rules))
    } catch {
      // Las reglas se mantienen en memoria si el navegador bloquea storage.
    }
    window.dispatchEvent(new CustomEvent('ads-veris-alerts-updated'))
  }, [rules, userId])

  const alerts = useMemo(
    () => metrics ? buildBusinessAlerts(metrics, rules) : [],
    [metrics, rules],
  )
  const filtered = alerts.filter((alert) => {
    const alertStatus = statuses[alert.id] ?? 'pendiente'
    return (severity === 'todas' || alert.severity === severity)
      && (status === 'todas' || alertStatus === status)
      && (origin === 'todos' || alert.origin === origin)
      && (!requestedSheet || alert.sheet === requestedSheet)
  })
  const pending = alerts.filter((alert) => (statuses[alert.id] ?? 'pendiente') === 'pendiente')
  const highPending = pending.filter((alert) => alert.severity === 'alta').length

  const updateStatus = (id: string, next: AlertStatus) => {
    setStatuses((current) => {
      const updated = { ...current, [id]: next }
      saveAlertStatuses(userId, datasetId, updated)
      return updated
    })
  }

  if (!ready) {
    return (
      <>
        <PageHeader title="Alertas" subtitle="Evidencia, impacto y acciones sobre tus datos reales." />
        <EmptyState
          icon={Bell}
          title="Sin datos para evaluar"
          description="Carga y limpia un archivo para detectar alertas comerciales, financieras y de calidad."
          ctaLabel="Cargar datos"
          ctaTo="/estandarizacion"
        />
      </>
    )
  }

  if (loading) {
    return (
      <>
        <PageHeader title="Alertas" subtitle="Evaluando señales sin duplicar el procesamiento…" />
        <div className="flex h-64 items-center justify-center gap-3 text-sm text-navy/60">
          <Loader2 className="h-6 w-6 animate-spin text-teal" />
          Preparando evidencia
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Alertas"
        subtitle="Prioriza problemas por severidad, estado y origen; abre directamente la evidencia que los provoca."
      />

      {error && (
        <Card className="mb-5 border-coral/35 bg-coral/5">
          <p className="text-sm text-coral">{error}</p>
        </Card>
      )}

      <section className="mb-5 grid gap-3 sm:grid-cols-3">
        <Summary label="Pendientes" value={pending.length} tone="text-navy" />
        <Summary label="Prioridad alta" value={highPending} tone="text-coral" />
        <Summary
          label="Revisadas o resueltas"
          value={alerts.length - pending.length}
          tone="text-teal"
        />
      </section>

      <Card className="mb-6 !p-4">
        {requestedSheet && (
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-teal/5 px-3 py-2 text-xs text-navy/65">
            <span>
              Mostrando alertas de la hoja <strong className="text-navy">{requestedSheet}</strong>.
            </span>
            <Link to="/alertas" className="font-semibold text-teal hover:underline">
              Ver todas
            </Link>
          </div>
        )}
        <div className="grid gap-3 md:grid-cols-3">
          <Filter
            label="Severidad"
            value={severity}
            onChange={(value) => setSeverity(value as AlertSeverity | 'todas')}
            options={[
              ['todas', 'Todas'],
              ['alta', 'Alta'],
              ['media', 'Media'],
              ['baja', 'Baja'],
            ]}
          />
          <Filter
            label="Estado"
            value={status}
            onChange={(value) => setStatus(value as AlertStatus | 'todas')}
            options={[
              ['todas', 'Todos'],
              ['pendiente', 'Pendiente'],
              ['revisada', 'Revisada'],
              ['resuelta', 'Resuelta'],
            ]}
          />
          <Filter
            label="Origen"
            value={origin}
            onChange={(value) => setOrigin(value as AlertOrigin | 'todos')}
            options={[
              ['todos', 'Todos'],
              ...Object.entries(ORIGIN).map(([value, meta]) => [value, meta.label]),
            ]}
          />
        </div>
      </Card>

      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <BellRing className={highPending > 0 ? 'h-5 w-5 text-coral' : 'h-5 w-5 text-gold'} />
          <h2 className="text-lg font-semibold text-navy">
            {filtered.length} alerta(s) en esta vista
          </h2>
        </div>

        {filtered.length === 0 ? (
          <Card className="border-green/25 bg-green/5">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="h-6 w-6 text-green" />
              <div>
                <p className="text-sm font-semibold text-navy">No hay alertas con estos filtros</p>
                <p className="text-xs text-navy/55">Cambia los filtros para ver las revisadas o resueltas.</p>
              </div>
            </div>
          </Card>
        ) : filtered.map((alert) => {
          const severityMeta = SEVERITY[alert.severity]
          const originMeta = ORIGIN[alert.origin]
          const Icon = originMeta.icon
          const alertStatus = statuses[alert.id] ?? 'pendiente'
          return (
            <Card key={alert.id} className={`border-l-4 ${severityMeta.border}`}>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-navy/[0.05]">
                  <Icon className="h-5 w-5 text-navy/65" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-semibold text-navy">{alert.title}</h3>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${severityMeta.pill}`}>
                      {severityMeta.label}
                    </span>
                    <span className="rounded-full bg-navy/5 px-2 py-0.5 text-[10px] font-medium text-navy/55">
                      {originMeta.label}
                    </span>
                    <span className="text-[10px] text-navy/40">{STATUS_LABEL[alertStatus]}</span>
                  </div>
                  <dl className="mt-3 grid gap-3 text-xs md:grid-cols-2">
                    <Detail label="Evidencia" value={alert.evidence} />
                    <Detail label="Impacto" value={alert.impact} />
                    <Detail label="Acción recomendada" value={alert.action} />
                    <Detail
                      label="Confianza"
                      value={`${Math.round(alert.confidence * 100).toLocaleString('es-CL')}%`}
                    />
                  </dl>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2 lg:w-48 lg:flex-col">
                  <Link
                    to={alert.target.to}
                    state={alert.target.state}
                    className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-teal px-3 py-2 text-xs font-semibold text-white hover:bg-teal/90"
                  >
                    {alert.target.label} <ExternalLink className="h-3.5 w-3.5" />
                  </Link>
                  {alertStatus === 'pendiente' && (
                    <button
                      type="button"
                      onClick={() => updateStatus(alert.id, 'revisada')}
                      className="rounded-lg border border-navy/15 px-3 py-2 text-xs font-semibold text-navy/65 hover:bg-navy/5"
                    >
                      Marcar revisada
                    </button>
                  )}
                  {alertStatus !== 'resuelta' && (
                    <button
                      type="button"
                      onClick={() => updateStatus(alert.id, 'resuelta')}
                      className="rounded-lg border border-green/25 px-3 py-2 text-xs font-semibold text-green hover:bg-green/5"
                    >
                      Marcar resuelta
                    </button>
                  )}
                  {alertStatus !== 'pendiente' && (
                    <button
                      type="button"
                      onClick={() => updateStatus(alert.id, 'pendiente')}
                      className="text-xs font-medium text-teal hover:underline"
                    >
                      Volver a pendiente
                    </button>
                  )}
                </div>
              </div>
            </Card>
          )
        })}
      </div>

      <Card className="mt-6">
        <div className="flex items-center gap-2">
          <Settings2 className="h-4.5 w-4.5 text-teal" />
          <h2 className="text-base font-semibold text-navy">Reglas configurables</h2>
        </div>
        <p className="mt-1 text-xs text-navy/55">
          Estas reglas complementan las validaciones financieras y de integridad del motor.
        </p>
        <div className="mt-4 divide-y divide-navy/5">
          <RuleRow
            label="Avisar si los ingresos caen más de"
            suffix="%"
            value={rules.caida_ingresos}
            onChange={(value) => setRules((current) => ({ ...current, caida_ingresos: value }))}
          />
          <RuleRow
            label="Avisar si el margen baja de"
            suffix="%"
            value={rules.margen_bajo}
            onChange={(value) => setRules((current) => ({ ...current, margen_bajo: value }))}
          />
          <RuleRow
            label="Avisar si un producto supera el"
            suffix="%"
            value={rules.concentracion_producto}
            onChange={(value) => setRules((current) => ({ ...current, concentracion_producto: value }))}
          />
          <RuleRow
            label="Avisar si un canal supera el"
            suffix="%"
            value={rules.concentracion_canal}
            onChange={(value) => setRules((current) => ({ ...current, concentracion_canal: value }))}
          />
          <div className="flex items-center justify-between py-3">
            <p className="text-sm text-navy/70">Incluir advertencias del motor</p>
            <Toggle
              checked={rules.advertencias_motor.activa}
              label="Incluir advertencias del motor"
              onChange={(checked) => setRules((current) => ({
                ...current,
                advertencias_motor: { activa: checked },
              }))}
            />
          </div>
        </div>
      </Card>
    </>
  )
}

function Summary({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <Card className="!p-4">
      <p className="text-xs text-navy/50">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${tone}`}>{value.toLocaleString('es-CL')}</p>
    </Card>
  )
}

function Filter({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[][]
  onChange: (value: string) => void
}) {
  return (
    <label className="text-xs font-medium text-navy/60">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1.5 w-full rounded-lg border border-navy/15 bg-white px-3 py-2 text-sm text-navy outline-none focus:border-teal"
      >
        {options.map(([option, text]) => <option key={option} value={option}>{text}</option>)}
      </select>
    </label>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-semibold text-navy/70">{label}</dt>
      <dd className="mt-1 leading-relaxed text-navy/55">{value}</dd>
    </div>
  )
}

function RuleRow({
  label,
  suffix,
  value,
  onChange,
}: {
  label: string
  suffix: string
  value: { activa: boolean; umbral_pct: number }
  onChange: (value: { activa: boolean; umbral_pct: number }) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 py-3">
      <Toggle
        checked={value.activa}
        label={label}
        onChange={(checked) => onChange({ ...value, activa: checked })}
      />
      <span className="min-w-0 flex-1 text-sm text-navy/70">{label}</span>
      <input
        type="number"
        min={0}
        max={100}
        value={value.umbral_pct}
        disabled={!value.activa}
        onChange={(event) => onChange({ ...value, umbral_pct: Number(event.target.value) })}
        className="w-20 rounded-lg border border-navy/15 px-2 py-1.5 text-right text-sm text-navy disabled:opacity-40"
      />
      <span className="w-8 text-xs text-navy/45">{suffix}</span>
    </div>
  )
}
