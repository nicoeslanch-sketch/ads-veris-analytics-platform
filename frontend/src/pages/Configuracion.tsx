/**
 * Configuración (SPEC §7 — Fase 5, MVP: perfil + preferencias + estado de cuenta).
 *
 * - Perfil y empresa: editable sobre la tabla profiles (RLS: solo el propio).
 * - Preferencias de datos: es-CL (lectura, desde profiles.preferences).
 * - Estado de la cuenta: plan + consultas IA usadas/límite del mes (GET /ai/usage).
 */

import { useEffect, useState } from 'react'
import { BadgeCheck, Crown, Loader2, Save, Sparkles } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import { useAuth } from '../auth/AuthContext'
import { apiGet } from '../lib/api'
import { fetchProfile, updateProfile } from '../lib/profile'
import { supabaseConfigured } from '../lib/supabase'
import { formatNumber } from '../lib/format'

interface AiUsage {
  disponible: boolean
  plan: 'basico' | 'gold'
  usadas: number
  limite: number
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

const FIELD_LABELS: Array<{ key: keyof FormState; label: string; placeholder: string }> = [
  { key: 'full_name', label: 'Nombre completo', placeholder: 'Ej: María Pérez' },
  { key: 'company', label: 'Empresa', placeholder: 'Ej: Comercial Andes SpA' },
  { key: 'rut', label: 'RUT de la empresa', placeholder: 'Ej: 76.123.456-7' },
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
  const meta = (user?.user_metadata ?? {}) as Record<string, string | undefined>

  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [plan, setPlan] = useState<'basico' | 'gold'>('basico')
  const [preferences, setPreferences] = useState<Record<string, unknown>>({})
  const [loading, setLoading] = useState(true)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'ok' | 'fail'>('idle')
  const [usage, setUsage] = useState<AiUsage | null>(null)

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
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSave = async () => {
    setSaveState('saving')
    const ok = await updateProfile({
      full_name: form.full_name || null,
      company: form.company || null,
      rut: form.rut || null,
      country: form.country || null,
      phone: form.phone || null,
    })
    setSaveState(ok ? 'ok' : 'fail')
  }

  const isGold = plan === 'gold'
  const usagePct =
    usage?.disponible && usage.limite > 0
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

      <div className="grid max-w-5xl gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        {/* Perfil y cuenta */}
        <Card className="h-fit">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-navy">Perfil y cuenta</h2>
            <Badge tone={isGold ? 'gold' : 'teal'}>
              {isGold ? 'Plan Gold' : 'Plan Básico'}
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
            {usage?.disponible ? (
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
            ) : (
              <p className="mt-3 text-sm text-navy/50">
                El contador de consultas se activa en producción (requiere Supabase y la
                migración 0006).
              </p>
            )}
          </Card>

          {/* Plan */}
          {!isGold && (
            <Card className="border-gold/30 bg-gold/5">
              <div className="flex items-center gap-2">
                <Crown className="h-4.5 w-4.5 text-gold" />
                <h2 className="text-base font-semibold text-navy">Mejora a Gold</h2>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-navy/60">
                Muchas más consultas IA al mes y limpieza personalizada con instrucciones
                propias. Disponible próximamente.
              </p>
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
