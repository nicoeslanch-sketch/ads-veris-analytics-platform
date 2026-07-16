/**
 * Planes (Fase 8) — Básico, Analista y Gold (en construcción).
 *
 * - Las tarjetas listan sus features desde la matriz única (lib/plans.ts,
 *   espejo de api/app/capabilities.py): una sola fuente de verdad.
 * - Sección "Tokens de limpieza dirigida": muestra el cupo mensual por plan
 *   (10 Analista / 25 Gold), el saldo de tokens addon (GET /plans/usage) y
 *   el botón "Solicitar más" (POST /addons/request).
 * - Botón "Contratar": pasa por startCheckout (lib/plans.ts) — la costura de
 *   la futura pasarela de pago. Hoy registra la solicitud y el administrador
 *   activa el plan desde Administrar cuentas.
 */

import { useEffect, useState } from 'react'
import {
  BadgeCheck,
  Check,
  Coins,
  Crown,
  Database,
  Gem,
  Hammer,
  Loader2,
  Minus,
  Send,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import { apiGet, apiPostJson, ApiError } from '../lib/api'
import { useAccess, type BillingIdentitySummary } from '../lib/access'
import { usePlan } from '../lib/usePlan'
import { TrialModal } from '../components/trial/TrialModal'
import { BillingIdentityForm, type RutType } from '../components/trial/BillingIdentityForm'
import {
  PLAN_CARDS,
  PLAN_ENFORCEMENT,
  PLAN_FEATURE_ROWS,
  startCheckout,
  type FeatureAvailability,
  type PlanCode,
} from '../lib/plans'
import { formatNumber } from '../lib/format'
import type { PlansUsage } from '../lib/types'

const PLAN_ICONS: Record<Exclude<PlanCode, 'sin_plan'>, typeof Sparkles> = {
  basico: Sparkles,
  analista: Crown,
  gold: Gem,
}

type RequestState = 'idle' | 'sending' | 'ok' | 'error'

function FeatureIcon({ availability }: { availability: FeatureAvailability }) {
  if (availability === 'si') return <Check className="h-4 w-4 shrink-0 text-green" />
  if (availability === 'limitado') return <Check className="h-4 w-4 shrink-0 text-teal" />
  if (availability === 'construccion') return <Hammer className="h-4 w-4 shrink-0 text-gold" />
  return <Minus className="h-4 w-4 shrink-0 text-navy/25" />
}

/** Fase 14b: al CONTRATAR, la solicitud viaja vinculada a la identidad de
 * facturación (RUT empresa o responsable). Si el usuario aún no la registró,
 * este modal abre el MISMO formulario compartido en contexto "contratacion";
 * la solicitud guarda `billing_identity_id`, jamás el RUT en texto libre. */
function BillingIdentityModal({
  open,
  planNombre,
  onClose,
  onSaved,
}: {
  open: boolean
  planNombre: string
  onClose: () => void
  onSaved: (identity: BillingIdentitySummary) => void
}) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setSubmitting(false)
      setError(null)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null

  const handleSubmit = async (rutType: RutType, rut: string) => {
    setSubmitting(true)
    setError(null)
    try {
      const result = await apiPostJson<{ guardada: boolean; identity: BillingIdentitySummary }>(
        '/me/billing-identity',
        { rut_type: rutType, rut },
      )
      onSaved(result.identity)
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'No se pudo guardar la identidad. Intenta nuevamente.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-deep/50 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Identidad de facturación"
    >
      <div
        className="relative max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          aria-label="Cerrar"
          className="absolute right-3 top-3 rounded-lg p-1 text-navy/40 transition-colors hover:bg-navy/5 hover:text-navy"
        >
          <X className="h-5 w-5" />
        </button>
        <h2 className="text-base font-semibold text-navy">
          Contratar el Plan {planNombre}
        </h2>
        <p className="mt-1 text-xs text-navy/55">
          Para gestionar la contratación y facturación necesitamos el RUT de la
          empresa o de la persona responsable.
        </p>
        <div className="mt-4">
          <BillingIdentityForm
            context="contratacion"
            submitLabel="Guardar y enviar solicitud"
            submitting={submitting}
            error={error}
            onSubmit={(rutType, rut) => void handleSubmit(rutType, rut)}
          />
        </div>
      </div>
    </div>
  )
}

function TrialBanner() {
  const { access } = useAccess()
  const [trialOpen, setTrialOpen] = useState(false)
  if (!access || access.is_admin || access.paid_plan !== 'sin_plan') return null

  const { trial } = access
  if (trial.active) {
    return (
      <div className="mb-6 flex flex-wrap items-center gap-3 rounded-lg border border-green/40 bg-green/5 px-4 py-3 text-sm text-navy/80">
        <Sparkles className="h-4 w-4 shrink-0 text-green" />
        <p className="min-w-0 flex-1">
          Tu <strong>prueba gratuita</strong> está activa: te quedan{' '}
          <strong>{trial.days_remaining} día(s)</strong>. Contrata un plan antes de
          que termine para no interrumpir tu trabajo (tus archivos se conservan).
        </p>
      </div>
    )
  }
  if (trial.used) {
    return (
      <div className="mb-6 flex flex-wrap items-center gap-3 rounded-lg border border-gold/40 bg-gold/10 px-4 py-3 text-sm text-navy/80">
        <Sparkles className="h-4 w-4 shrink-0 text-gold" />
        <p className="min-w-0 flex-1">
          Tu prueba gratuita terminó. Contrata un plan para seguir procesando tus
          datos — tus archivos siguen guardados según la retención de tu cuenta.
        </p>
      </div>
    )
  }
  return (
    <div className="mb-6 flex flex-wrap items-center gap-3 rounded-lg border border-gold/50 bg-gold/10 px-4 py-3 text-sm text-navy/80">
      <TrialModal open={trialOpen} onClose={() => setTrialOpen(false)} />
      <Sparkles className="h-4 w-4 shrink-0 text-gold" />
      <p className="min-w-0 flex-1">
        ¿Aún no te decides? Prueba la plataforma <strong>gratis por 15 días</strong>{' '}
        con tus propios datos (sin tarjeta; no incluye el asistente IA).
      </p>
      <button
        onClick={() => setTrialOpen(true)}
        className="shrink-0 rounded-lg bg-gold px-4 py-2 text-xs font-semibold text-navy-deep transition-colors hover:bg-gold/90"
      >
        Probar demo gratuita (15 días)
      </button>
    </div>
  )
}

export default function Planes() {
  const { plan: currentPlan, isAdmin, loading: planLoading } = usePlan()
  const { access, applyAccess, refresh } = useAccess()
  const [usage, setUsage] = useState<PlansUsage | null>(null)
  const [requestStates, setRequestStates] = useState<Record<string, RequestState>>({})
  const [requestError, setRequestError] = useState<string | null>(null)
  // Fase 14b: plan pendiente de contratación mientras se registra el RUT
  const [identityFlow, setIdentityFlow] = useState<
    { code: Exclude<PlanCode, 'sin_plan'>; nombre: string } | null
  >(null)

  useEffect(() => {
    let cancelled = false
    apiGet<PlansUsage>('/plans/usage')
      .then((info) => {
        if (!cancelled) setUsage(info)
      })
      .catch(() => {
        if (!cancelled) setUsage(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const sendRequest = async (tipo: string, mensaje: string, billingIdentityId?: string) => {
    setRequestStates((prev) => ({ ...prev, [tipo]: 'sending' }))
    setRequestError(null)
    try {
      await apiPostJson('/addons/request', {
        tipo,
        mensaje,
        ...(billingIdentityId ? { billing_identity_id: billingIdentityId } : {}),
      })
      setRequestStates((prev) => ({ ...prev, [tipo]: 'ok' }))
    } catch (err) {
      setRequestStates((prev) => ({ ...prev, [tipo]: 'error' }))
      setRequestError(
        err instanceof ApiError ? err.message : 'No se pudo registrar la solicitud.',
      )
    }
  }

  /** Botón "Contratar": costura de la pasarela de pago (Fase 9). Hoy el
   * checkout no redirige, así que la contratación queda como solicitud y el
   * administrador activa el plan desde Administrar cuentas.
   * Fase 14b: la solicitud exige la identidad de facturación — si no está
   * registrada, se abre el formulario de RUT (contexto contratación) y la
   * solicitud sale vinculada a billing_identity_id. */
  const contratar = (code: Exclude<PlanCode, 'sin_plan'>, nombre: string) => {
    const checkout = startCheckout(code)
    if (checkout.redirected) return
    const identity = access?.billing_identity
    if (identity?.id) {
      void sendRequest(`upgrade_${code}`, `Quiero contratar el Plan ${nombre}.`, identity.id)
      return
    }
    setIdentityFlow({ code, nombre })
  }

  const handleIdentitySaved = (identity: BillingIdentitySummary) => {
    const pending = identityFlow
    setIdentityFlow(null)
    // El contexto único conoce la identidad al instante (sin recargar)
    if (access) applyAccess({ ...access, billing_identity: identity })
    else refresh()
    if (pending) {
      void sendRequest(
        `upgrade_${pending.code}`,
        `Quiero contratar el Plan ${pending.nombre}.`,
        identity.id,
      )
    }
  }

  const limpieza = usage?.disponible ? usage.limpieza : null
  const unlimitedCleaning = Boolean(isAdmin || limpieza?.ilimitado)
  const restantesBase = limpieza && !unlimitedCleaning
    ? Math.max(limpieza.base - limpieza.usadas_mes, 0)
    : null

  return (
    <>
      <PageHeader
        title="Planes"
        subtitle="Elige cuánto trabajo le entregas a tu analista de datos. Del dato al criterio."
      />

      {isAdmin && (
        <div className="mb-6 flex items-start gap-3 rounded-lg border border-gold/40 bg-gold/5 px-4 py-3 text-sm text-navy/80">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-gold" />
          <p>
            <strong>Cuenta administradora con acceso total.</strong> Todas las capacidades
            están habilitadas y las cuotas de IA y limpieza dirigida son ilimitadas.
          </p>
        </div>
      )}

      {!PLAN_ENFORCEMENT && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-teal/40 bg-teal/5 px-4 py-3 text-sm text-navy/80">
          <BadgeCheck className="mt-0.5 h-4 w-4 shrink-0 text-teal" />
          <p>
            Los planes están en preparación: hoy <strong>todas las funciones están
            desbloqueadas</strong> para que las pruebes. Cuando se activen, cada plan
            mantendrá exactamente lo que ves aquí.
          </p>
        </div>
      )}

      {/* Fase 14: prueba gratuita — banner para cuentas sin plan que no la
          usaron, y estado con días restantes mientras está vigente. */}
      <TrialBanner />

      {/* Fase 14b: registro del RUT de facturación al contratar */}
      <BillingIdentityModal
        open={identityFlow !== null}
        planNombre={identityFlow?.nombre ?? ''}
        onClose={() => setIdentityFlow(null)}
        onSaved={handleIdentitySaved}
      />

      {/* ── Tarjetas de planes ── */}
      <div className="grid gap-6 lg:grid-cols-3">
        {PLAN_CARDS.map(({ code, nombre, tagline, enConstruccion, destacado }) => {
          const Icon = PLAN_ICONS[code]
          const esActual = !planLoading && !isAdmin && currentPlan === code
          const upgradeTipo = `upgrade_${code}`
          const upgradeState = requestStates[upgradeTipo] ?? 'idle'
          return (
            <Card
              key={code}
              className={`flex flex-col ${
                destacado ? 'border-gold/50 shadow-md ring-1 ring-gold/20' : ''
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <div
                    className={`flex h-10 w-10 items-center justify-center rounded-xl ${
                      code === 'basico'
                        ? 'bg-teal/10'
                        : code === 'analista'
                          ? 'bg-gold/15'
                          : 'bg-navy/10'
                    }`}
                  >
                    <Icon
                      className={`h-5 w-5 ${
                        code === 'basico'
                          ? 'text-teal'
                          : code === 'analista'
                            ? 'text-gold'
                            : 'text-navy'
                      }`}
                    />
                  </div>
                  <h2 className="text-lg font-bold text-navy">Plan {nombre}</h2>
                </div>
                {enConstruccion && <Badge tone="gold">En construcción</Badge>}
                {esActual && !enConstruccion && <Badge tone="teal">Tu plan actual</Badge>}
              </div>

              <p className="mt-2 text-sm leading-relaxed text-navy/60">{tagline}</p>

              <ul className="mt-4 flex-1 space-y-2.5">
                {PLAN_FEATURE_ROWS.map(({ label, availability }) => {
                  const value = availability[code]
                  return (
                    <li key={label} className="flex items-start gap-2 text-sm">
                      <span className="mt-0.5">
                        <FeatureIcon availability={value} />
                      </span>
                      <span
                        className={
                          value === 'no' ? 'text-navy/35 line-through decoration-navy/20' : 'text-navy/75'
                        }
                      >
                        {label}
                        {value === 'limitado' && (
                          <span className="ml-1 text-xs font-medium text-teal">(limitado)</span>
                        )}
                        {value === 'construccion' && (
                          <span className="ml-1 text-xs font-medium text-gold">(pronto)</span>
                        )}
                      </span>
                    </li>
                  )
                })}
              </ul>

              {code === 'gold' && (
                <div className="mt-4 flex items-center gap-3 rounded-lg bg-navy/5 px-3 py-2 text-xs text-navy/60">
                  <Database className="h-4 w-4 shrink-0 text-navy/50" />
                  <Users className="h-4 w-4 shrink-0 text-navy/50" />
                  <span>SQL + comunidad: lo estamos construyendo.</span>
                </div>
              )}

              <div className="mt-5">
                {isAdmin ? (
                  <div className="rounded-lg border border-gold/40 bg-gold/5 px-4 py-2.5 text-center text-sm font-semibold text-navy">
                    Incluido en tu acceso administrador
                  </div>
                ) : esActual ? (
                  <div className="rounded-lg border border-teal/40 bg-teal/5 px-4 py-2.5 text-center text-sm font-semibold text-teal">
                    Este es tu plan
                  </div>
                ) : enConstruccion ? (
                  <button
                    disabled
                    className="w-full cursor-not-allowed rounded-lg border border-navy/15 px-4 py-2.5 text-sm font-semibold text-navy/40"
                  >
                    Próximamente
                  </button>
                ) : upgradeState === 'ok' ? (
                  <div className="rounded-lg border border-green/40 bg-green/5 px-4 py-2.5 text-center text-sm font-medium text-green">
                    Solicitud recibida: activamos tu plan y te avisamos
                  </div>
                ) : (
                  <>
                    <button
                      onClick={() => contratar(code, nombre)}
                      disabled={upgradeState === 'sending'}
                      className={`inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                        destacado
                          ? 'bg-gold text-navy-deep hover:bg-gold/90'
                          : 'bg-navy text-white hover:bg-navy-deep'
                      }`}
                    >
                      {upgradeState === 'sending' ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Send className="h-4 w-4" />
                      )}
                      Contratar este plan
                    </button>
                    {upgradeState === 'error' && requestError && (
                      <p className="mt-1.5 text-center text-xs text-coral">{requestError}</p>
                    )}
                    <p className="mt-1.5 text-center text-[11px] text-navy/40">
                      Pago en línea próximamente; hoy coordinamos contigo la activación.
                      {access?.billing_identity
                        ? ` Facturación: RUT ${access.billing_identity.rut_masked} (${access.billing_identity.rut_type}).`
                        : ' Al contratar te pediremos el RUT de facturación.'}
                    </p>
                  </>
                )}
              </div>
            </Card>
          )
        })}
      </div>

      {/* ── Tokens / addons de limpieza dirigida ── */}
      <Card className="mt-8 border-gold/30">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="min-w-0 max-w-xl">
            <div className="flex items-center gap-2">
              <Coins className="h-5 w-5 text-gold" />
              <h2 className="text-base font-semibold text-navy">
                Tokens de limpieza dirigida (addons)
              </h2>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-navy/60">
              {unlimitedCleaning ? (
                <>
                  Tu cuenta administradora tiene <strong>limpieza dirigida ilimitada</strong>{' '}
                  y no necesita tokens adicionales.
                </>
              ) : (
                <>
                  La limpieza dirigida con tus propias variables incluye{' '}
                  <strong>10 intentos al mes (25 en Gold)</strong> en los planes Analista y
                  Gold. Si necesitas más, solicita tokens adicionales: se pagan aparte,
                  nosotros los agregamos a tu cuenta y no expiran.
                </>
              )}
            </p>
            {usage && !usage.disponible && (
              <p className="mt-2 text-xs text-navy/45">Disponible próximamente.</p>
            )}
          </div>

          <div className="flex flex-col items-stretch gap-3 sm:min-w-[260px]">
            {unlimitedCleaning ? (
              <div className="rounded-xl border border-gold/30 bg-gold/5 p-4">
                <p className="flex items-center justify-center gap-2 text-sm font-semibold text-navy">
                  <ShieldCheck className="h-4 w-4 text-gold" /> Sin límite mensual
                </p>
              </div>
            ) : limpieza && limpieza.base === 0 ? (
              <div className="rounded-xl bg-navy/5 p-4 text-sm text-navy/60">
                No incluida en tu plan actual. Está disponible desde el Plan Analista.
              </div>
            ) : limpieza && (
              <div className="rounded-xl bg-navy/5 p-4">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wide text-navy/50">
                    Intentos del mes
                  </span>
                  <span className="text-lg font-bold text-navy">
                    {formatNumber(limpieza.usadas_mes)}
                    <span className="text-sm font-medium text-navy/50"> / {limpieza.base}</span>
                  </span>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-navy/10">
                  <div
                    className={`h-full rounded-full ${restantesBase === 0 ? 'bg-coral' : 'bg-teal'}`}
                    style={{
                      width: `${Math.min(100, (limpieza.usadas_mes / Math.max(limpieza.base, 1)) * 100)}%`,
                    }}
                  />
                </div>
                <p className="mt-2.5 flex items-center justify-between text-xs text-navy/60">
                  <span>Tokens adicionales</span>
                  <span className="font-bold text-gold">{formatNumber(limpieza.addons)}</span>
                </p>
              </div>
            )}
            {unlimitedCleaning ? null : requestStates['tokens_limpieza'] === 'ok' ? (
              <div className="rounded-lg border border-green/40 bg-green/5 px-4 py-2.5 text-center text-sm font-medium text-green">
                Recibimos tu solicitud: nos pondremos en contacto contigo
              </div>
            ) : (
              <button
                onClick={() =>
                  void sendRequest('tokens_limpieza', 'Quiero tokens adicionales de limpieza dirigida.')
                }
                disabled={requestStates['tokens_limpieza'] === 'sending'}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-gold px-5 py-2.5 text-sm font-semibold text-navy-deep transition-colors hover:bg-gold/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {requestStates['tokens_limpieza'] === 'sending' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Coins className="h-4 w-4" />
                )}
                Solicitar más tokens
              </button>
            )}
          </div>
        </div>
        {requestError && (
          <p className="mt-4 rounded-lg border border-coral/40 bg-coral/5 px-4 py-2.5 text-sm text-coral">
            {requestError}
          </p>
        )}
      </Card>
    </>
  )
}
