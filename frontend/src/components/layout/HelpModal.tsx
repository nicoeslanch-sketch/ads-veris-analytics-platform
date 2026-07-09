/** Modal de ayuda (Fase 8) — botón "¿Necesitas ayuda?" del sidebar.
 *
 * El usuario escribe qué necesita y la solicitud llega a la bandeja del
 * administrador (Administrar cuentas → semáforo rojo). Sin IA: responde
 * una persona del equipo ADS Veris.
 */

import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { CheckCircle2, HelpCircle, Loader2, Send, X } from 'lucide-react'
import { ApiError, apiPostJson } from '../../lib/api'

export default function HelpModal({ onClose }: { onClose: () => void }) {
  const location = useLocation()
  const [mensaje, setMensaje] = useState('')
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const enviar = async () => {
    if (!mensaje.trim()) {
      setError('Cuéntanos en qué necesitas ayuda.')
      return
    }
    setSending(true)
    setError(null)
    try {
      await apiPostJson('/support/request', {
        mensaje: mensaje.trim(),
        pagina: location.pathname,
      })
      setSent(true)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'No se pudo enviar la solicitud. Intenta nuevamente.',
      )
    } finally {
      setSending(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-deep/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-teal/10">
              <HelpCircle className="h-5 w-5 text-teal" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-navy">¿Necesitas ayuda?</h2>
              <p className="text-xs text-navy/55">Te responde una persona del equipo ADS Veris.</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-navy/40 transition-colors hover:bg-navy/5 hover:text-navy"
            aria-label="Cerrar"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {sent ? (
          <div className="mt-5 flex flex-col items-center gap-3 rounded-xl bg-green/5 px-6 py-8 text-center">
            <CheckCircle2 className="h-8 w-8 text-green" />
            <p className="text-sm font-semibold text-navy">¡Solicitud enviada!</p>
            <p className="text-xs text-navy/60">
              Recibimos tu mensaje y te responderemos lo antes posible al correo de tu cuenta.
            </p>
            <button
              onClick={onClose}
              className="mt-1 rounded-lg bg-navy px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-navy-deep"
            >
              Listo
            </button>
          </div>
        ) : (
          <>
            <textarea
              value={mensaje}
              onChange={(e) => {
                setMensaje(e.target.value)
                setError(null)
              }}
              rows={5}
              maxLength={2000}
              autoFocus
              placeholder="Escribe aquí tu consulta: qué intentabas hacer, qué archivo usabas y qué pasó…"
              className="mt-4 w-full resize-y rounded-lg border border-navy/20 bg-white px-3.5 py-2.5 text-sm text-navy outline-none transition-colors placeholder:text-navy/35 focus:border-teal"
            />
            {error && (
              <p className="mt-2 rounded-lg border border-coral/40 bg-coral/5 px-3 py-2 text-xs text-coral">
                {error}
              </p>
            )}
            <div className="mt-4 flex items-center justify-between gap-3">
              <p className="text-[11px] text-navy/40">
                La solicitud queda ligada a tu cuenta; no compartas contraseñas.
              </p>
              <button
                onClick={() => void enviar()}
                disabled={sending}
                className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-teal px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal/90 disabled:cursor-not-allowed disabled:bg-teal/50"
              >
                {sending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Enviando…
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4" /> Enviar solicitud
                  </>
                )}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
