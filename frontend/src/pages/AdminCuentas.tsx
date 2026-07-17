/** Administrar cuentas (Fase 8) — SOLO para la cuenta administradora.
 *
 * - Lista todas las cuentas de ADS Veris con semáforo: rojo = tiene
 *   solicitudes pendientes (ayuda o tokens), verde = al día.
 * - Detalle por cuenta: datos visibles (nunca contraseñas), plan actual y
 *   activación manual de planes (hasta que exista la pasarela de pago, y
 *   como respaldo después).
 * - Bandeja de soporte unificada: responder y marcar atendidas.
 *
 * El backend valida is_admin en cada endpoint: esta página es solo la vista.
 */

import { useCallback, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Coins,
  CreditCard,
  Inbox,
  Loader2,
  Mail,
  RefreshCw,
  ShieldCheck,
  UserRound,
  Users,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import { ApiError, apiGet, apiPostJson } from '../lib/api'
import { normalizePlan, planLabel, type PlanCode } from '../lib/plans'
import { usePlan } from '../lib/usePlan'

interface AdminAccount {
  id: string
  email: string | null
  nombre: string | null
  empresa: string | null
  pais: string | null
  telefono: string | null
  plan: PlanCode
  is_admin: boolean
  creado: string | null
  ultimo_acceso: string | null
  datasets: number
  solicitudes_pendientes: number
}

interface AccountsResponse {
  cuentas: AdminAccount[]
  totales: { cuentas: number; solicitudes_pendientes: number }
}

interface SupportItem {
  origen: 'ayuda' | 'addon'
  id: string
  user_id: string
  mensaje: string | null
  pagina?: string | null
  tipo?: string
  status: 'pendiente' | 'atendida'
  respuesta?: string | null
  billing_identity_id?: string | null
  billing_identity?: {
    id: string
    rut_type: 'empresa' | 'responsable'
    rut_masked: string
  } | null
  created_at: string
}

interface SupportResponse {
  solicitudes: SupportItem[]
  pendientes: number
}

const PLAN_OPTIONS: PlanCode[] = ['basico', 'analista', 'gold']

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('es-CL', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function AdminCuentas() {
  const { isAdmin, loading: planLoading } = usePlan()

  const [data, setData] = useState<AccountsResponse | null>(null)
  const [support, setSupport] = useState<SupportResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [savingPlan, setSavingPlan] = useState<string | null>(null)
  const [attending, setAttending] = useState<string | null>(null)
  const [grantingTo, setGrantingTo] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const refresh = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.all([
      apiGet<AccountsResponse>('/admin/accounts'),
      apiGet<SupportResponse>('/admin/support'),
    ])
      .then(([accounts, inbox]) => {
        setData(accounts)
        setSupport(inbox)
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'No se pudo cargar el panel.'),
      )
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (isAdmin) refresh()
  }, [isAdmin, refresh])

  // Guardia de ruta: mientras carga el perfil no decidimos; si no es admin, fuera.
  if (planLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-teal" />
      </div>
    )
  }
  if (!isAdmin) return <Navigate to="/" replace />

  const cambiarPlan = async (userId: string, plan: string) => {
    setSavingPlan(userId)
    setNotice(null)
    try {
      await apiPostJson(`/admin/accounts/${userId}/plan`, { plan })
      setNotice(`Plan ${planLabel(plan).replace('Plan ', '')} activado correctamente.`)
      setData((prev) =>
        prev
          ? {
              ...prev,
              cuentas: prev.cuentas.map((c) =>
                c.id === userId ? { ...c, plan: plan as PlanCode } : c,
              ),
            }
          : prev,
      )
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : 'No se pudo cambiar el plan.')
    } finally {
      setSavingPlan(null)
    }
  }

  const otorgarTokens = async (userId: string) => {
    const cantidad = window.prompt('¿Cuántos tokens de limpieza dirigida quieres otorgar?', '5')
    if (!cantidad) return
    const credits = Number.parseInt(cantidad, 10)
    if (!Number.isFinite(credits) || credits <= 0) {
      setNotice('Cantidad inválida: escribe un número mayor que 0.')
      return
    }
    setGrantingTo(userId)
    setNotice(null)
    try {
      const result = await apiPostJson<{ saldo: number }>('/admin/grant-credits', {
        user_id: userId,
        credits,
        note: 'Otorgado desde Administrar cuentas',
      })
      setNotice(`Tokens otorgados. Saldo addon actual: ${result.saldo}.`)
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : 'No se pudieron otorgar los tokens.')
    } finally {
      setGrantingTo(null)
    }
  }

  const atender = async (item: SupportItem) => {
    const respuesta =
      item.origen === 'ayuda'
        ? window.prompt('Respuesta para el usuario (opcional):', '') ?? undefined
        : undefined
    setAttending(item.id)
    try {
      const path =
        item.origen === 'ayuda'
          ? `/admin/support/${item.id}/attend`
          : `/admin/addon-requests/${item.id}/attend`
      await apiPostJson(path, respuesta ? { respuesta } : {})
      refresh()
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : 'No se pudo marcar como atendida.')
    } finally {
      setAttending(null)
    }
  }

  const emailOf = (userId: string) =>
    data?.cuentas.find((c) => c.id === userId)?.email ?? userId.slice(0, 8)

  const pendientes = support?.solicitudes.filter((s) => s.status === 'pendiente') ?? []

  return (
    <>
      <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <PageHeader
          className="!mb-0"
          title="Administrar cuentas 🛡️"
          subtitle="Todas las cuentas de ADS Veris: estado, plan, solicitudes y activación manual."
        />
        <button
          onClick={refresh}
          disabled={loading}
          className="inline-flex w-full shrink-0 items-center justify-center gap-2 rounded-lg border border-navy/20 bg-white px-4 py-2.5 text-sm font-medium text-navy transition-colors hover:bg-navy/5 disabled:opacity-60 sm:w-auto"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Actualizar
        </button>
      </div>

      {notice && (
        <div className="mb-4 rounded-lg border border-teal/40 bg-teal/5 px-4 py-2.5 text-sm text-navy/80">
          {notice}
        </div>
      )}
      {error && (
        <Card className="mb-6 border-coral/40 bg-coral/5">
          <p className="text-sm text-coral">{error}</p>
        </Card>
      )}

      {/* Totales */}
      {data && (
        <div className="grid gap-4 sm:grid-cols-3">
          <Card className="!p-4 bg-gradient-to-br from-teal/5 to-transparent">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-teal/10">
                <Users className="h-5 w-5 text-teal" />
              </div>
              <div>
                <p className="text-xs text-navy/50">Cuentas totales</p>
                <p className="text-xl font-bold text-navy">{data.totales.cuentas}</p>
              </div>
            </div>
          </Card>
          <Card className="!p-4 bg-gradient-to-br from-coral/5 to-transparent">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-coral/10">
                <Inbox className="h-5 w-5 text-coral" />
              </div>
              <div>
                <p className="text-xs text-navy/50">Solicitudes pendientes</p>
                <p className="text-xl font-bold text-navy">
                  {data.totales.solicitudes_pendientes}
                </p>
              </div>
            </div>
          </Card>
          <Card className="!p-4 bg-gradient-to-br from-gold/5 to-transparent">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gold/15">
                <CreditCard className="h-5 w-5 text-gold" />
              </div>
              <div>
                {/* Fase 15: "distinto de basico" contaba cuentas SIN plan como
                    pagadas y excluía a los Básico (que sí son contratables).
                    Se cuenta plan asignado real; el estado de PAGO vendrá de
                    `subscriptions` cuando exista la pasarela. */}
                <p className="text-xs text-navy/50">Cuentas con plan asignado</p>
                <p className="text-xl font-bold text-navy">
                  {
                    data.cuentas.filter((c) =>
                      ['basico', 'analista', 'gold'].includes(normalizePlan(c.plan)),
                    ).length
                  }
                </p>
              </div>
            </div>
          </Card>
        </div>
      )}

      {loading && !data ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-teal" />
        </div>
      ) : (
        data && (
          <div className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
            {/* Lista de cuentas */}
            <Card className="min-w-0">
              <h2 className="text-base font-semibold text-navy">Cuentas</h2>
              <p className="mt-0.5 text-sm text-navy/55">
                🔴 con solicitudes pendientes · 🟢 al día. Haz clic para ver el detalle y
                activar planes.
              </p>
              <ul className="mt-4 divide-y divide-navy/5">
                {data.cuentas.map((cuenta) => {
                  const abierto = expanded === cuenta.id
                  return (
                    <li key={cuenta.id}>
                      <button
                        onClick={() => setExpanded(abierto ? null : cuenta.id)}
                        className="flex w-full items-center gap-3 py-3 text-left transition-colors hover:bg-navy/[0.02]"
                      >
                        <span
                          className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                            cuenta.solicitudes_pendientes > 0 ? 'bg-coral' : 'bg-green'
                          }`}
                          title={
                            cuenta.solicitudes_pendientes > 0
                              ? `${cuenta.solicitudes_pendientes} solicitud(es) pendiente(s)`
                              : 'Sin pendientes'
                          }
                        />
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-navy/5">
                          {cuenta.is_admin ? (
                            <ShieldCheck className="h-4.5 w-4.5 text-gold" />
                          ) : (
                            <UserRound className="h-4.5 w-4.5 text-navy/50" />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold text-navy">
                            {cuenta.nombre || cuenta.email || cuenta.id.slice(0, 8)}
                          </p>
                          <p className="truncate text-xs text-navy/50">
                            {cuenta.email} {cuenta.empresa ? `· ${cuenta.empresa}` : ''}
                          </p>
                        </div>
                        <Badge tone={cuenta.is_admin || cuenta.plan !== 'basico' ? 'gold' : 'navy'}>
                          {cuenta.is_admin
                            ? 'Administrador'
                            : planLabel(cuenta.plan).replace('Plan ', '')}
                        </Badge>
                        {cuenta.solicitudes_pendientes > 0 && (
                          <span className="rounded-full bg-coral/10 px-2 py-0.5 text-xs font-bold text-coral">
                            {cuenta.solicitudes_pendientes}
                          </span>
                        )}
                        {abierto ? (
                          <ChevronUp className="h-4 w-4 shrink-0 text-navy/40" />
                        ) : (
                          <ChevronDown className="h-4 w-4 shrink-0 text-navy/40" />
                        )}
                      </button>

                      {abierto && (
                        <div className="mb-3 rounded-xl bg-navy/[0.03] p-4">
                          <div className="grid gap-3 text-xs sm:grid-cols-2">
                            <p>
                              <span className="text-navy/50">Registro:</span>{' '}
                              <span className="font-medium text-navy">{formatDate(cuenta.creado)}</span>
                            </p>
                            <p>
                              <span className="text-navy/50">Último acceso:</span>{' '}
                              <span className="font-medium text-navy">{formatDate(cuenta.ultimo_acceso)}</span>
                            </p>
                            <p>
                              <span className="text-navy/50">Archivos cargados:</span>{' '}
                              <span className="font-medium text-navy">{cuenta.datasets}</span>
                            </p>
                            <p>
                              <span className="text-navy/50">País / Teléfono:</span>{' '}
                              <span className="font-medium text-navy">
                                {cuenta.pais || '—'} {cuenta.telefono ? `· ${cuenta.telefono}` : ''}
                              </span>
                            </p>
                          </div>

                          <div className="mt-4 flex flex-wrap items-center gap-3">
                            <label className="flex items-center gap-2 text-xs font-semibold text-navy/60">
                              Activar plan:
                              <select
                                value={cuenta.plan}
                                disabled={savingPlan === cuenta.id}
                                onChange={(e) => void cambiarPlan(cuenta.id, e.target.value)}
                                className="rounded-lg border border-navy/20 bg-white px-3 py-1.5 text-xs font-medium text-navy outline-none focus:border-teal"
                              >
                                {PLAN_OPTIONS.map((p) => (
                                  <option key={p} value={p}>
                                    {planLabel(p).replace('Plan ', '')}
                                  </option>
                                ))}
                              </select>
                              {savingPlan === cuenta.id && (
                                <Loader2 className="h-3.5 w-3.5 animate-spin text-teal" />
                              )}
                            </label>
                            <button
                              onClick={() => void otorgarTokens(cuenta.id)}
                              disabled={grantingTo === cuenta.id}
                              className="inline-flex items-center gap-1.5 rounded-lg border border-gold/50 px-3 py-1.5 text-xs font-semibold text-gold transition-colors hover:bg-gold/10 disabled:opacity-50"
                            >
                              {grantingTo === cuenta.id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Coins className="h-3.5 w-3.5" />
                              )}
                              Otorgar tokens
                            </button>
                          </div>
                          <p className="mt-3 text-[11px] leading-relaxed text-navy/45">
                            La activación es manual mientras habilitamos el pago en línea; cuando
                            exista la pasarela, el pago confirmado activará el plan por esta misma
                            vía y este selector quedará como respaldo.
                          </p>
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            </Card>

            {/* Bandeja de soporte */}
            <div className="flex flex-col gap-6">
              <Card className="border-coral/20">
                <div className="flex items-center gap-2">
                  <Inbox className="h-4.5 w-4.5 text-coral" />
                  <h2 className="text-base font-semibold text-navy">Bandeja de entrada</h2>
                  {pendientes.length > 0 && (
                    <span className="rounded-full bg-coral/10 px-2 py-0.5 text-xs font-bold text-coral">
                      {pendientes.length}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-navy/55">
                  Solicitudes de ayuda y de tokens/upgrade, de la más nueva a la más antigua.
                </p>
                {support && support.solicitudes.length === 0 ? (
                  <div className="mt-4 flex flex-col items-center gap-2 rounded-xl bg-green/5 px-4 py-8 text-center">
                    <CheckCircle2 className="h-6 w-6 text-green" />
                    <p className="text-sm font-medium text-navy/70">Bandeja al día 🎉</p>
                  </div>
                ) : (
                  <ul className="mt-4 space-y-3">
                    {(support?.solicitudes ?? []).slice(0, 20).map((item) => (
                      <li
                        key={`${item.origen}-${item.id}`}
                        className={`rounded-xl border p-3.5 ${
                          item.status === 'pendiente'
                            ? 'border-coral/30 bg-coral/[0.04]'
                            : 'border-navy/10 bg-white opacity-70'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          {item.origen === 'ayuda' ? (
                            <Mail className="h-3.5 w-3.5 shrink-0 text-teal" />
                          ) : (
                            <Coins className="h-3.5 w-3.5 shrink-0 text-gold" />
                          )}
                          <p className="min-w-0 flex-1 truncate text-xs font-semibold text-navy">
                            {emailOf(item.user_id)}
                          </p>
                          <span className="shrink-0 text-[10px] text-navy/40">
                            {formatDate(item.created_at)}
                          </span>
                        </div>
                        <p className="mt-1.5 text-xs leading-relaxed text-navy/70">
                          {item.origen === 'addon' && item.tipo ? (
                            <strong className="text-gold">[{item.tipo.replace('_', ' ')}] </strong>
                          ) : null}
                          {item.mensaje || 'Sin mensaje.'}
                        </p>
                        {item.origen === 'addon' && item.billing_identity && (
                          <div className="mt-2 flex min-w-0 items-start gap-1.5 text-[10px] leading-relaxed text-navy/55">
                            <CreditCard className="mt-0.5 h-3 w-3 shrink-0 text-teal" />
                            <span className="min-w-0">
                              Facturación:{' '}
                              {item.billing_identity.rut_type === 'empresa'
                                ? 'empresa'
                                : 'responsable'}{' '}
                              · RUT{' '}
                              <strong className="text-navy/70">
                                {item.billing_identity.rut_masked}
                              </strong>
                              <span className="block break-all text-navy/35">
                                ID {item.billing_identity.id}
                              </span>
                            </span>
                          </div>
                        )}
                        {item.status === 'pendiente' ? (
                          <button
                            onClick={() => void atender(item)}
                            disabled={attending === item.id}
                            className="mt-2.5 inline-flex items-center gap-1.5 rounded-lg bg-navy px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-navy-deep disabled:opacity-50"
                          >
                            {attending === item.id ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <CheckCircle2 className="h-3 w-3" />
                            )}
                            Marcar atendida
                          </button>
                        ) : (
                          <p className="mt-2 flex items-center gap-1 text-[10px] font-semibold text-green">
                            <CheckCircle2 className="h-3 w-3" /> Atendida
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </Card>

              <Card className="border-navy/10 bg-gradient-to-br from-navy/[0.03] to-transparent !p-4">
                <div className="flex items-start gap-2.5">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-navy/50" />
                  <p className="text-xs leading-relaxed text-navy/60">
                    Aquí ves solo datos visibles de cada cuenta (nunca contraseñas). Todo cambio
                    manual queda registrado en la auditoría del sistema.
                  </p>
                </div>
              </Card>
            </div>
          </div>
        )
      )}
    </>
  )
}
