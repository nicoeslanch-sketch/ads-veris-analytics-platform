/** Modal de activación de la prueba gratuita de 15 días (Fase 14).
 *
 * Envía POST /me/trial (el RUT viaja SOLO en el body). Al activarse, aplica
 * el AccessInfo devuelto al contexto único — los botones de subir/procesar se
 * habilitan al instante, sin recargar la página. Los errores llegan del
 * backend ya redactados (específicos si son del propio usuario, genéricos si
 * involucran a terceros — jamás se revela qué cuenta usó un RUT).
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, Sparkles, X } from 'lucide-react'
import { ApiError, apiPostJson } from '../../lib/api'
import { useAccess, type AccessInfo } from '../../lib/access'
import { BillingIdentityForm, type RutType } from './BillingIdentityForm'

interface TrialActivationResponse {
  activada: boolean
  rut_confirmado: string
  access: AccessInfo
}

const TRIAL_FEATURES = [
  'Estandariza y limpia tus archivos Excel, CSV y Google Sheets',
  'Dashboard de indicadores, Explorar datos, Alertas e Historial',
  'Reporte ejecutivo del negocio (PDF)',
]

export function TrialModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { applyAccess } = useAccess()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<TrialActivationResponse | null>(null)

  if (!open) return null

  const handleSubmit = async (rutType: RutType, rut: string) => {
    setSubmitting(true)
    setError(null)
    try {
      const result = await apiPostJson<TrialActivationResponse>('/me/trial', {
        rut_type: rutType,
        rut,
      })
      applyAccess(result.access)
      setSuccess(result)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo activar la prueba. Intenta nuevamente.')
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
      aria-label="Activar prueba gratuita de 15 días"
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

        {success ? (
          <div className="text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green/15">
              <CheckCircle2 className="h-6 w-6 text-green" />
            </div>
            <h2 className="mt-3 text-base font-semibold text-navy">¡Prueba activada!</h2>
            <p className="mt-1.5 text-sm leading-relaxed text-navy/60">
              Tienes <strong className="text-navy">{success.access.trial.days_remaining} días</strong>{' '}
              para probar la plataforma con tus propios datos (RUT registrado:{' '}
              {success.rut_confirmado}). El asistente con IA no está incluido en la
              prueba: se activa desde el Plan Básico.
            </p>
            <Link
              to="/estandarizacion"
              onClick={onClose}
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-teal px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal/90"
            >
              Subir mi primer archivo
            </Link>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gold/15">
                <Sparkles className="h-5.5 w-5.5 text-gold" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-navy">
                  Prueba gratuita — 15 días
                </h2>
                <p className="text-xs text-navy/55">
                  Sin tarjeta. Una prueba por cuenta y por RUT.
                </p>
              </div>
            </div>

            <ul className="mt-4 space-y-1.5">
              {TRIAL_FEATURES.map((feature) => (
                <li key={feature} className="flex items-start gap-2 text-xs text-navy/70">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal" />
                  {feature}
                </li>
              ))}
              <li className="flex items-start gap-2 text-xs text-navy/50">
                <X className="mt-0.5 h-3.5 w-3.5 shrink-0 text-navy/35" />
                El asistente con IA y la descarga de la base limpia se activan con un plan.
              </li>
            </ul>

            <div className="mt-4">
              <BillingIdentityForm
                context="trial"
                submitLabel="Activar mi prueba gratuita"
                submitting={submitting}
                error={error}
                onSubmit={(rutType, rut) => void handleSubmit(rutType, rut)}
              />
            </div>
          </>
        )}
      </div>
    </div>
  )
}
