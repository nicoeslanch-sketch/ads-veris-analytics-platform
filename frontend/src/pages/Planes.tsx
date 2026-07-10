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
  Sparkles,
  Users,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import { apiGet, apiPostJson, ApiError } from '../lib/api'
import { usePlan } from '../lib/usePlan'
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

const PLAN_ICONS: Record<PlanCode, typeof Sparkles> = {
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

export default function Planes() {
  const { plan: currentPlan, loading: planLoading } = usePlan()
  const [usage, setUsage] = useState<PlansUsage | null>(null)
  const [requestStates, setRequestStates] = useState<Record<string, RequestState>>({})
  const [requestError, setRequestError] = useState<string | null>(null)

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

  const sendRequest = async (tipo: string, mensaje: string) => {
    setRequestStates((prev) => ({ ...prev, [tipo]: 'sending' }))
    setRequestError(null)
    try {
      await apiPostJson('/addons/request', { tipo, mensaje })
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
   * administrador activa el plan desde Administrar cuentas. */
  const contratar = (code: PlanCode, nombre: string) => {
    const checkout = startCheckout(code)
    if (!checkout.redirected) {
      void sendRequest(`upgrade_${code}`, `Quiero contratar el Plan ${nombre}.`)
    }
  }

  const limpieza = usage?.disponible ? usage.limpieza : null
  const restantesBase = limpieza ? Math.max(limpieza.base - limpieza.usadas_mes, 0) : null

  return (
    <>
      <PageHeader
        title="Planes"
        subtitle="Elige cuánto trabajo le entregas a tu analista de datos. Del dato al criterio."
      />

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

      {/* ── Tarjetas de planes ── */}
      <div className="grid gap-6 lg:grid-cols-3">
        {PLAN_CARDS.map(({ code, nombre, tagline, enConstruccion, destacado }) => {
          const Icon = PLAN_ICONS[code]
          const esActual = !planLoading && currentPlan === code
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
                {esActual ? (
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
                    <p className="mt-1.5 text-center text-[11px] text-navy/40">
                      Pago en línea próximamente; hoy coordinamos contigo la activación.
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
              La limpieza dirigida con tus propias variables incluye{' '}
              <strong>{limpieza ? `${limpieza.base} intentos al mes` : '10 intentos al mes (25 en Gold)'}</strong>{' '}
              en los planes Analista y Gold. Si necesitas más, solicita tokens
              adicionales: se pagan aparte, nosotros los agregamos a tu cuenta y no
              expiran.
            </p>
            {usage && !usage.disponible && (
              <p className="mt-2 text-xs text-navy/45">
                El contador se activa en producción (requiere Supabase y las migraciones
                0008 y 0009).
              </p>
            )}
          </div>

          <div className="flex flex-col items-stretch gap-3 sm:min-w-[260px]">
            {limpieza && (
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
            {requestStates['tokens_limpieza'] === 'ok' ? (
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
