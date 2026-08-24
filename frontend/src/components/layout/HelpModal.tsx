/** Chat humano de Ayuda: usuario ↔ cuenta administradora ADS Veris. */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Clock3, Headphones, Instagram, Loader2, LockKeyhole, Mail,
  MessageCircle, Send, UserRound, X,
} from 'lucide-react'
import { ApiError, apiGet, apiPostJson } from '../../lib/api'
import { CONTACT_EMAIL, INSTAGRAM_URL, WHATSAPP_URL, WhatsAppIcon } from './ContactLinks'

interface SupportMessage {
  id: string
  sender_role: 'customer' | 'admin' | 'system'
  body: string
  created_at: string
}

interface Conversation {
  id: string
  status: 'open' | 'closed'
  source_page: string | null
  created_at: string
  last_message_at: string
  closed_at: string | null
  messages: SupportMessage[]
}

interface ChatResponse {
  available: boolean
  conversation: Conversation | null
  expires_after_hours: number
}

function timeLabel(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })
}

export default function HelpModal({ onClose }: { onClose: () => void }) {
  const location = useLocation()
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [available, setAvailable] = useState(true)
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [startNew, setStartNew] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const response = await apiGet<ChatResponse>('/support/conversation')
      setAvailable(response.available)
      setConversation(response.conversation)
      if (response.conversation?.status === 'open') setStartNew(false)
    } catch {
      setAvailable(false)
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load(true)
    }, 10_000)
    const onVisible = () => document.visibilityState === 'visible' && void load(true)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [load])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversation?.messages.length])

  const send = async () => {
    const clean = message.trim()
    if (!clean || sending) return
    setSending(true)
    setError(null)
    try {
      const response = await apiPostJson<ChatResponse>('/support/messages', {
        message: clean,
        conversation_id: conversation?.status === 'open' && !startNew ? conversation.id : null,
        page: location.pathname,
      })
      setConversation(response.conversation)
      setAvailable(response.available)
      setStartNew(false)
      setMessage('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo enviar el mensaje.')
    } finally {
      setSending(false)
    }
  }

  const activeConversation = conversation?.status === 'open' && !startNew
  const shownMessages = startNew ? [] : conversation?.messages ?? []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-deep/55 p-3 sm:p-5" onClick={onClose}>
      <div className="flex h-[min(760px,92vh)] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl" onClick={(event) => event.stopPropagation()}>
        <header className="flex items-start justify-between border-b border-navy/10 px-5 py-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-teal/10"><Headphones className="h-5 w-5 text-teal" /></div>
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-navy">Soporte ADS Veris</h2>
              <p className="text-xs leading-relaxed text-navy/55">Chat directo con la cuenta administradora principal.</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-navy/40 transition-colors hover:bg-navy/5 hover:text-navy" aria-label="Cerrar ayuda"><X className="h-5 w-5" /></button>
        </header>

        <div className="flex items-center gap-2 border-b border-gold/25 bg-gold/[0.08] px-5 py-2.5 text-[11px] leading-relaxed text-navy/65 sm:px-6">
          <Clock3 className="h-3.5 w-3.5 shrink-0 text-gold" />
          La conversación se elimina automáticamente después de 24 horas sin mensajes.
        </div>

        <main className="min-h-0 flex-1 overflow-y-auto bg-slate-50/70 px-4 py-5 sm:px-6">
          {loading ? (
            <div className="flex h-full items-center justify-center gap-2 text-sm text-navy/50"><Loader2 className="h-5 w-5 animate-spin text-teal" /> Abriendo conversación…</div>
          ) : !available ? (
            <div className="mx-auto mt-12 max-w-sm rounded-xl border border-gold/30 bg-white p-5 text-center">
              <LockKeyhole className="mx-auto h-7 w-7 text-gold" />
              <p className="mt-3 text-sm font-semibold text-navy">Chat temporalmente no disponible</p>
              <p className="mt-1.5 text-xs leading-relaxed text-navy/55">Puedes usar los canales directos que aparecen abajo mientras terminamos de habilitarlo.</p>
            </div>
          ) : shownMessages.length === 0 ? (
            <div className="mx-auto flex h-full max-w-md flex-col items-center justify-center text-center">
              <MessageCircle className="h-10 w-10 text-teal/50" />
              <p className="mt-4 text-sm font-semibold text-navy">{startNew ? 'Nueva conversación' : '¿En qué podemos ayudarte?'}</p>
              <p className="mt-2 text-xs leading-relaxed text-navy/55">Describe qué intentabas hacer, en qué pantalla estabas y qué ocurrió. No compartas contraseñas ni datos personales.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {shownMessages.map((item) => {
                const customer = item.sender_role === 'customer'
                if (item.sender_role === 'system') {
                  return <div key={item.id} className="flex justify-center"><p className="rounded-full bg-navy/5 px-3 py-1 text-[11px] font-medium text-navy/55">{item.body}</p></div>
                }
                return (
                  <div key={item.id} className={`flex ${customer ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[86%] rounded-2xl px-3.5 py-2.5 shadow-sm ${customer ? 'rounded-br-md bg-teal text-white' : 'rounded-bl-md border border-navy/10 bg-white text-navy'}`}>
                      <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold opacity-70">
                        {customer ? <UserRound className="h-3 w-3" /> : <Headphones className="h-3 w-3" />}
                        {customer ? 'Tú' : 'Soporte ADS Veris'} · {timeLabel(item.created_at)}
                      </div>
                      <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{item.body}</p>
                    </div>
                  </div>
                )
              })}
              <div ref={bottomRef} />
            </div>
          )}
        </main>

        {conversation?.status === 'closed' && !startNew && (
          <div className="border-t border-navy/10 bg-navy/[0.03] px-5 py-3 sm:px-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div><p className="text-sm font-semibold text-navy">Conversación cerrada</p><p className="text-xs text-navy/50">Este hilo ya no admite mensajes.</p></div>
              <button onClick={() => setStartNew(true)} className="rounded-lg bg-teal px-4 py-2 text-xs font-semibold text-white hover:bg-teal/90">Iniciar otra conversación</button>
            </div>
          </div>
        )}

        {available && (!conversation || activeConversation || startNew) && (
          <div className="border-t border-navy/10 bg-white px-4 py-3 sm:px-6">
            {error && <p className="mb-2 rounded-lg border border-coral/30 bg-coral/5 px-3 py-2 text-xs text-coral">{error}</p>}
            <div className="flex items-end gap-2 rounded-xl border border-navy/15 px-3 py-2 focus-within:border-teal">
              <textarea value={message} onChange={(event) => { setMessage(event.target.value); setError(null) }} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send() } }} rows={2} maxLength={4000} placeholder="Escribe tu solicitud…" className="max-h-28 min-h-10 flex-1 resize-none bg-transparent text-sm text-navy outline-none placeholder:text-navy/35" />
              <button onClick={() => void send()} disabled={sending || !message.trim()} className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-teal text-white transition-colors hover:bg-teal/90 disabled:bg-navy/10 disabled:text-navy/30" aria-label="Enviar mensaje">{sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}</button>
            </div>
          </div>
        )}

        <footer className="flex flex-wrap items-center gap-2 border-t border-navy/10 bg-white px-5 py-2.5 sm:px-6">
          <span className="mr-1 text-[10px] font-semibold uppercase tracking-wide text-navy/35">Canales directos</span>
          <a href={WHATSAPP_URL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[11px] font-semibold text-green"><WhatsAppIcon className="h-3 w-3" /> WhatsApp</a>
          <a href={INSTAGRAM_URL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[11px] font-semibold text-coral"><Instagram className="h-3 w-3" /> Instagram</a>
          <a href={`mailto:${CONTACT_EMAIL}`} className="inline-flex min-w-0 items-center gap-1 text-[11px] font-semibold text-teal"><Mail className="h-3 w-3 shrink-0" /> <span className="truncate">{CONTACT_EMAIL}</span></a>
        </footer>
      </div>
    </div>
  )
}
