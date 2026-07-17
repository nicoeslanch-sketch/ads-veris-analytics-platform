/**
 * Configuración (SPEC §7 — Fase 5, MVP: perfil + preferencias + estado de cuenta).
 *
 * - Perfil y empresa: editable sobre la tabla profiles (RLS: solo el propio).
 * - Preferencias de datos: es-CL (lectura, desde profiles.preferences).
 * - Estado de la cuenta: plan + consultas IA usadas/límite del mes (GET /ai/usage).
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BadgeCheck, Crown, Loader2, Save, ShieldCheck, Sparkles, Wand2 } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import { useAuth } from '../auth/AuthContext'
import { useAccess } from '../lib/access'
import { apiGet } from '../lib/api'
import { fetchProfile, updateProfile } from '../lib/profile'
import { supabaseConfigured } from '../lib/supabase'
import { formatNumber } from '../lib/format'
import { isAnalystPlan, planLabel, type PlanCode } from '../lib/plans'
import type { PlansUsage } from '../lib/types'

interface AiUsage {
  disponible: boolean
  plan: PlanCode
  usadas: number
  limite: number
  ilimitado?: boolean
  periodo?: string
}

interface FormState {
  full_name: string
  company: string
  rut: string
  country: string
  phone: string
}

const EMPTY_FORM: FormState = { full_name: '', company: '', rut: '', country: '', phone: '' }

// Fase 15: el RUT sale de este formulario — existían DOS fuentes (profiles.rut
// editable aquí en texto libre y billing_identities validada con módulo 11 al
// contratar/activar la prueba). La fuente ÚNICA es billing_identities: aquí
// solo se muestra enmascarada (read-only); profiles.rut queda como legado.
const FIELD_LABELS: Array<{ key: keyof FormState; label: string; placeholder: string }> = [
  { key: 'full_name', label: 'Nombre completo', placeholder: 'Ej: María Pérez' },
  { key: 'company', label: 'Empresa', placeholder: 'Ej: Comercial Andes SpA' },
  { key: 'country', label: 'País', placeholder: 'Ej: Chile' },
  { key: 'phone', label: 'Teléfono', placeholder: 'Ej: +56 9 1234 5678' },
]

const DEFAULT_PREFERENCES: Record<string, string | number> = {
  currency: 'CLP',
  date_format: 'DD/MM/YYYY',
  decimal_separator: ',',
  rounding: 0,
  timezone: 'America/Santiago',
}

const PREFERENCE_LABELS: Record<string, string> = {
  currency: 'Moneda',
  date_format: 'Formato de fecha',
  decimal_separator: 'Separador decimal',
  rounding: 'Redondeo (decimales)',
  timezone: 'Zona horaria',
}

export default function Configuracion() {
  const { user } = useAuth()
  const { access } = useAccess()
  const meta = (user?.user_metadata ?? {}) as Record<string, string | undefined>

  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [plan, setPlan] = useState<PlanCode>('basico')
  const [preferences, setPreferences] = useState<Record<string, unknown>>({})
  const [loading, setLoading] = useState(true)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'ok' | 'fail'>('idle')
  const [usage, setUsage] = useState<AiUsage | null>(null)
  const [plansUsage, setPlansUsage] = useState<PlansUsage | null>(null)
  // Bug: mientras /ai/usage y /plans/usage estaban en vuelo, `usage`/
  // `plansUsage` seguían en null y las tarjetas mostraban "Disponible
  // próximamente" — indistinguible de una cuenta administradora sin cupo
  // ilimitado detectado todavía. Loading explícito en vez de inferirlo de null.
  const [usageLoading, setUsageLoading] = useState(true)
  const [plansUsageLoading, setPlansUsageLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetchProfile().then((profile) => {
      if (cancelled) return
      setForm({
        full_name: profile?.full_name ?? meta.full_name ?? '',
        company: profile?.company ?? meta.company ?? '',
        rut: profile?.rut ?? '',
        country: profile?.country ?? meta.country ?? '',
        phone: profile?.phone ?? meta.phone ?? '',
      })
      if (profile?.plan) setPlan(profile.plan)
      if (profile?.preferences) setPreferences(profile.preferences)
      setLoading(false)
    })
    apiGet<AiUsage>('/ai/usage')
      .then((info) => {
        if (!cancelled) setUsage(info)
      })
      .catch(() => {
        if (!cancelled) setUsage(null)
      })
      .finally(() => {
        if (!cancelled) setUsageLoading(false)
      })
    apiGet<PlansUsage>('/plans/usage')
      .then((info) => {
        if (!cancelled) setPlansUsage(info)
      })
      .catch(() => {
        if (!cancelled) setPlansUsage(null)
      })
      .finally(() => {
        if (!cancelled) setPlansUsageLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSave = async () => {
    setSaveState('saving')
    // Fase 15: el RUT ya NO se escribe desde aquí — la fuente única es
    // billing_identities (validada con módulo 11 al contratar o activar la
    // prueba). profiles.rut queda como campo legado, intacto.
    const ok = await updateProfile({
      full_name: form.full_name || null,
      company: form.company || null,
      country: form.country || null,
      phone: form.phone || null,
    })
    setSaveState(ok ? 'ok' : 'fail')
  }

  const isAnalyst = isAnalystPlan(plan)
  const isAdmin = Boolean(access?.is_admin)
  const usagePct =
    usage?.disponible && !usage.ilimitado && usage.limite > 0
      ? Math.min(100, (usage.usadas / usage.limite) * 100)
      : 0

  const inputClass =
    'w-full rounded-lg border border-navy/20 bg-white px-3 py-2 text-sm text-navy outline-none transition-colors focus:border-teal'

  return (
    <>
      <PageHeader
        title="Configuración"
        subtitle="Tu perfil, tu empresa y las preferencias de datos de la plataforma."
      />

      <div className="grid max-w-5xl items-start gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        {/* Perfil y cuenta */}
        <Card className="h-fit">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-semibold text-navy">Perfil y cuenta</h2>
            <Badge tone={isAdmin || isAnalyst ? 'gold' : 'teal'}>
              {isAdmin ? 'Administrador · acceso total' : planLabel(plan)}
            </Badge>
          </div>

          {loading ? (
            <div className="flex h-40 items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-teal" />
            </div>
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-navy/50 sm:col-span-2">
                  Correo (no editable)
                  <input
                    value={user?.email ?? ''}
                    disabled
                    className={`${inputClass} bg-navy/5 text-navy/60`}
                  />
                </label>
                {FIELD_LABELS.map(({ key, label, placeholder }) => (
                  <label
                    key={key}
                    className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-navy/50"
                  >
                    {label}
                    <input
                      value={form[key]}
                      placeholder={placeholder}
                      onChange={(e) => {
                        setForm((prev) => ({ ...prev, [key]: e.target.value }))
                        setSaveState('idle')
                      }}
                      className={inputClass}
                    />
                  </label>
                ))}
                {/* Fase 15: fuente ÚNICA del RUT = billing_identities —
                    aquí solo se muestra enmascarado, jamás se edita libre. */}
                <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-navy/50">
                  RUT de facturación
                  <input
                    value={
                      access?.billing_identity
                        ? `${access.billing_identity.rut_masked} (${access.billing_identity.rut_type})`
                        : 'Se registra al contratar un plan o activar la prueba'
                    }
                    disabled
                    className={`${inputClass} bg-navy/5 text-navy/60`}
                  />
                  <span className="text-[10px] font-normal normal-case tracking-normal text-navy/45">
                    Validado con dígito verificador y protegido. Para corregirlo,
                    escríbenos a servicios@adsveris.com.
                  </span>
                </label>
              </div>
              <div className="mt-5 flex items-center gap-3">
                <button
                  onClick={() => void handleSave()}
                  disabled={saveState === 'saving' || !supabaseConfigured}
                  className="inline-flex items-center gap-2 rounded-lg bg-teal px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal/90 disabled:cursor-not-allowed disabled:bg-teal/50"
                  title={supabaseConfigured ? undefined : 'Requiere Supabase configurado'}
                >
                  {saveState === 'saving' ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  Guardar cambios
                </button>
                {saveState === 'ok' && (
                  <span className="flex items-center gap-1 text-sm font-medium text-green">
                    <BadgeCheck className="h-4 w-4" /> Perfil actualizado
                  </span>
                )}
                {saveState === 'fail' && (
                  <span className="text-sm font-medium text-coral">
                    No se pudo guardar. Revisa tu conexión con Supabase.
                  </span>
                )}
              </div>
            </>
          )}
        </Card>

        <div className="flex flex-col gap-6">
          {/* Estado de la cuenta: consultas IA */}
          <Card>
            <div className="flex items-center gap-2">
              <Sparkles className="h-4.5 w-4.5 text-gold" />
              <h2 className="text-base font-semibold text-navy">Consultas IA del mes</h2>
            </div>
            {usageLoading ? (
              <div className="mt-3 space-y-2">
                <div className="h-7 w-24 animate-pulse rounded bg-navy/10" />
                <div className="h-2 w-full animate-pulse rounded-full bg-navy/10" />
              </div>
            ) : usage?.disponible ? (
              usage.ilimitado ? (
                <div className="mt-3 rounded-lg border border-gold/35 bg-gold/5 px-3 py-3">
                  <p className="flex items-center gap-2 text-sm font-semibold text-navy">
                    <ShieldCheck className="h-4 w-4 text-gold" /> Uso ilimitado
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-navy/55">
                    La cuenta administradora no tiene límite mensual de consultas IA.
                  </p>
                </div>
              ) : (
                <>
                <p className="mt-3 text-2xl font-bold text-navy">
                  {formatNumber(usage.usadas)}
                  <span className="text-base font-medium text-navy/50">
                    {' '}
                    / {formatNumber(usage.limite)}
                  </span>
                </p>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-navy/10">
                  <div
                    className={`h-full rounded-full ${usagePct >= 90 ? 'bg-coral' : 'bg-teal'}`}
                    style={{ width: `${usagePct}%` }}
                  />
                </div>
                <p className="mt-2 text-xs text-navy/50">
                  Cada resumen, pregunta al asistente y recomendación descuenta 1 del cupo.
                  Se renueva cada mes.
                </p>
                </>
              )
            ) : (
              <p className="mt-3 text-sm text-navy/50">Disponible próximamente.</p>
            )}
          </Card>

          {/* Fase 7: limpieza dirigida IA + tokens addon */}
          <Card>
            <div className="flex items-center gap-2">
              <Wand2 className="h-4.5 w-4.5 text-teal" />
              <h2 className="text-base font-semibold text-navy">Limpieza dirigida IA del mes</h2>
            </div>
            {plansUsageLoading ? (
              <div className="mt-3 space-y-2">
                <div className="h-7 w-24 animate-pulse rounded bg-navy/10" />
                <div className="h-2 w-full animate-pulse rounded-full bg-navy/10" />
              </div>
            ) : plansUsage?.disponible ? (
              plansUsage.limpieza.ilimitado ? (
                <div className="mt-3 rounded-lg border border-teal/30 bg-teal/5 px-3 py-3">
                  <p className="flex items-center gap-2 text-sm font-semibold text-navy">
                    <ShieldCheck className="h-4 w-4 text-teal" /> Uso ilimitado
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-navy/55">
                    La cuenta administradora puede ejecutar limpiezas dirigidas sin cupo mensual.
                  </p>
                </div>
              ) : plansUsage.limpieza.base === 0 ? (
                <p className="mt-3 text-sm text-navy/50">
                  No incluida en tu plan actual. Está disponible desde el Plan Analista.
                </p>
              ) : (
                <>
                <p className="mt-3 text-2xl font-bold text-navy">
                  {formatNumber(plansUsage.limpieza.usadas_mes)}
                  <span className="text-base font-medium text-navy/50">
                    {' '}
                    / {formatNumber(plansUsage.limpieza.base)}
                  </span>
                </p>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-navy/10">
                  <div
                    className={`h-full rounded-full ${
                      plansUsage.limpieza.usadas_mes >= plansUsage.limpieza.base
                        ? 'bg-coral'
                        : 'bg-teal'
                    }`}
                    style={{
                      width: `${Math.min(
                        100,
                        (plansUsage.limpieza.usadas_mes / Math.max(plansUsage.limpieza.base, 1)) * 100,
                      )}%`,
                    }}
                  />
                </div>
                <p className="mt-2 flex items-center justify-between text-xs text-navy/55">
                  <span>Tokens adicionales</span>
                  <span className="font-bold text-gold">
                    {formatNumber(plansUsage.limpieza.addons)}
                  </span>
                </p>
                </>
              )
            ) : (
              <p className="mt-3 text-sm text-navy/50">Disponible próximamente.</p>
            )}
            <Link
              to="/planes"
              className="mt-3 block text-xs font-semibold text-teal hover:underline"
            >
              Ver planes y solicitar tokens →
            </Link>
          </Card>

          {/* Plan */}
          {!isAdmin && !isAnalyst && (
            <Card className="border-gold/30 bg-gold/5">
              <div className="flex items-center gap-2">
                <Crown className="h-4.5 w-4.5 text-gold" />
                <h2 className="text-base font-semibold text-navy">Mejora a Analista</h2>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-navy/60">
                Descarga tu base limpia y dirige la limpieza con tus propias
                variables (10 intentos al mes en Analista, 25 en Gold, + tokens).
              </p>
              <Link
                to="/planes"
                className="mt-3 block w-full rounded-lg bg-gold px-4 py-2 text-center text-sm font-semibold text-navy-deep transition-colors hover:bg-gold/90"
              >
                Ver planes
              </Link>
            </Card>
          )}

          {/* Preferencias de datos */}
          <Card>
            <h2 className="text-base font-semibold text-navy">Preferencias de datos</h2>
            <dl className="mt-3 divide-y divide-navy/5">
              {Object.entries(PREFERENCE_LABELS).map(([key, label]) => (
                <div key={key} className="flex items-center justify-between py-2.5">
                  <dt className="text-sm text-navy/60">{label}</dt>
                  <dd className="text-sm font-medium text-navy">
                    {String(preferences[key] ?? DEFAULT_PREFERENCES[key])}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-3 text-xs text-navy/40">
              La plataforma opera en es-CL: pesos chilenos, punto de miles y fechas
              DD/MM/YYYY.
            </p>
          </Card>
        </div>
      </div>
    </>
  )
}
