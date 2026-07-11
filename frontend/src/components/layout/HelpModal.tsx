/** Modal de ayuda (Fase 8) — botón "¿Necesitas ayuda?" del sidebar.
 *
 * El usuario escribe qué necesita y la solicitud llega a la bandeja del
 * administrador (Administrar cuentas → semáforo rojo). Sin IA: responde
 * una persona del equipo ADS Veris.
 */

import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { CheckCircle2, Clock, HelpCircle, Instagram, Loader2, Mail, MessageCircle, Send, X } from 'lucide-react'
import { ApiError, apiGet, apiPostJson } from '../../lib/api'
import { CONTACT_EMAIL, INSTAGRAM_URL, WHATSAPP_URL, WhatsAppIcon } from './ContactLinks'

interface MyRequest {
  id: string
  mensaje: string
  status: 'pendiente' | 'atendida'
  respuesta: string | null
  created_at: string
}

export default function HelpModal({ onClose }: { onClose: () => void }) {
  const location = useLocation()
  const [mensaje, setMensaje] = useState('')
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mine, setMine] = useState<MyRequest[]>([])

  // Solicitudes anteriores del usuario (con la respuesta del equipo, si la hay).
  useEffect(() => {
    apiGet<{ disponible: boolean; solicitudes: MyRequest[] }>('/support/mine')
      .then((res) => setMine(res.solicitudes ?? []))
      .catch(() => setMine([]))
  }, [sent])

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
              Recibimos tu mensaje: el equipo ADS Veris lo revisará a la brevedad. La
              respuesta quedará registrada en tu cuenta.
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

            {/* Fase 11 §1: canales directos — WhatsApp, Instagram y correo */}
            <div className="mt-5 border-t border-navy/10 pt-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-navy/45">
                También puedes escribirnos directo
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <a
                  href={WHATSAPP_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-green/10 px-3 py-1.5 text-xs font-semibold text-green transition-colors hover:bg-green hover:text-white"
                >
                  <WhatsAppIcon className="h-3.5 w-3.5" /> WhatsApp
                </a>
                <a
                  href={INSTAGRAM_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-coral/10 px-3 py-1.5 text-xs font-semibold text-coral transition-colors hover:bg-coral hover:text-white"
                >
                  <Instagram className="h-3.5 w-3.5" /> @adsveris
                </a>
                <a
                  href={`mailto:${CONTACT_EMAIL}`}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-teal/10 px-3 py-1.5 text-xs font-semibold text-teal transition-colors hover:bg-teal hover:text-white"
                >
                  <Mail className="h-3.5 w-3.5" /> {CONTACT_EMAIL}
                </a>
              </div>
            </div>

            {mine.length > 0 && (
              <div className="mt-5 border-t border-navy/10 pt-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-navy/45">
                  Mis solicitudes
                </p>
                <ul className="mt-2 max-h-40 space-y-2 overflow-y-auto pr-1">
                  {mine.slice(0, 5).map((req) => (
                    <li key={req.id} className="rounded-lg bg-navy/[0.04] px-3 py-2">
                      <div className="flex items-center gap-2">
                        {req.status === 'atendida' ? (
                          <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-green" />
                        ) : (
                          <Clock className="h-3.5 w-3.5 shrink-0 text-gold" />
                        )}
                        <p className="min-w-0 flex-1 truncate text-xs text-navy/70">{req.mensaje}</p>
                        <span className="shrink-0 text-[10px] font-semibold text-navy/45">
                          {req.status === 'atendida' ? 'Respondida' : 'Pendiente'}
                        </span>
                      </div>
                      {req.respuesta && (
                        <p className="mt-1.5 flex items-start gap-1.5 rounded-md bg-teal/[0.07] px-2 py-1.5 text-[11px] leading-relaxed text-navy/75">
                          <MessageCircle className="mt-0.5 h-3 w-3 shrink-0 text-teal" />
                          {req.respuesta}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
