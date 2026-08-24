import { useCallback, useEffect, useRef, useState } from 'react'
import { CheckCircle2, Headphones, Loader2, MessageCircle, RefreshCw, Send, UserRound, XCircle } from 'lucide-react'
import Card from '../ui/Card'
import { ApiError, apiGet, apiPostJson } from '../../lib/api'

interface ChatSummary {
  id: string
  user_id: string
  status: 'open' | 'closed'
  source_page: string | null
  created_at: string
  last_message_at: string
  closed_at: string | null
  message_count: number
  last_message: { sender_role: string; body: string; created_at: string } | null
}

interface ChatMessage {
  id: string
  sender_role: 'customer' | 'admin' | 'system'
  body: string
  created_at: string
}

interface ChatDetail extends Omit<ChatSummary, 'message_count' | 'last_message'> {
  messages: ChatMessage[]
}

function dateTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('es-CL', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export default function AdminSupportChat({ accounts }: { accounts: Array<{ id: string; email: string | null; nombre: string | null }> }) {
  const [conversations, setConversations] = useState<ChatSummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<ChatDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const labelFor = useCallback((userId: string) => {
    const account = accounts.find((item) => item.id === userId)
    return account?.nombre || account?.email || userId.slice(0, 8)
  }, [accounts])

  const loadList = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const response = await apiGet<{ conversations: ChatSummary[]; open: number }>('/admin/support/conversations')
      setConversations(response.conversations)
      setSelected((current) => current && response.conversations.some((item) => item.id === current) ? current : response.conversations[0]?.id ?? null)
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudieron cargar las conversaciones.')
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [])

  const loadDetail = useCallback(async (id: string, quiet = false) => {
    try {
      const response = await apiGet<{ conversation: ChatDetail }>(`/admin/support/conversations/${id}`)
      setDetail(response.conversation)
      if (!quiet) window.setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 0)
    } catch (err) {
      if (!quiet) setError(err instanceof ApiError ? err.message : 'No se pudo abrir la conversación.')
    }
  }, [])

  useEffect(() => { void loadList() }, [loadList])
  useEffect(() => { if (selected) void loadDetail(selected) }, [selected, loadDetail])
  useEffect(() => {
    const interval = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return
      void loadList(true)
      if (selected) void loadDetail(selected, true)
    }, 10_000)
    return () => window.clearInterval(interval)
  }, [selected, loadList, loadDetail])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [detail?.messages.length])

  const send = async () => {
    if (!selected || !message.trim() || sending) return
    setSending(true)
    try {
      const response = await apiPostJson<{ conversation: ChatDetail }>(`/admin/support/conversations/${selected}/messages`, { message: message.trim() })
      setDetail(response.conversation)
      setMessage('')
      void loadList(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo enviar la respuesta.')
    } finally {
      setSending(false)
    }
  }

  const close = async () => {
    if (!selected || !window.confirm('¿Cerrar esta conversación? El cliente verá “Conversación cerrada”.')) return
    try {
      await apiPostJson(`/admin/support/conversations/${selected}/close`, {})
      await Promise.all([loadList(true), loadDetail(selected)])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cerrar la conversación.')
    }
  }

  return (
    <Card className="mt-6 overflow-hidden !p-0">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-navy/10 px-5 py-4">
        <div>
          <div className="flex items-center gap-2"><MessageCircle className="h-5 w-5 text-teal" /><h2 className="text-base font-semibold text-navy">Conversaciones de soporte</h2><span className="rounded-full bg-coral/10 px-2 py-0.5 text-xs font-bold text-coral">{conversations.filter((item) => item.status === 'open').length}</span></div>
          <p className="mt-1 text-xs text-navy/50">Responde como la cuenta principal. Los hilos caducan tras 24 horas sin actividad.</p>
        </div>
        <button onClick={() => void loadList()} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg border border-navy/15 px-3 py-2 text-xs font-semibold text-navy/70 hover:bg-navy/5"><RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} /> Actualizar</button>
      </div>
      {error && <p className="m-4 rounded-lg border border-coral/30 bg-coral/5 px-3 py-2 text-xs text-coral">{error}</p>}
      <div className="grid min-h-[440px] md:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="max-h-[560px] overflow-y-auto border-r border-navy/10 bg-navy/[0.02]">
          {loading && conversations.length === 0 ? <div className="flex h-full items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-teal" /></div> : conversations.length === 0 ? <div className="p-8 text-center"><CheckCircle2 className="mx-auto h-6 w-6 text-green" /><p className="mt-2 text-sm text-navy/60">Sin conversaciones activas.</p></div> : conversations.map((item) => (
            <button key={item.id} onClick={() => setSelected(item.id)} className={`block w-full border-b border-navy/5 px-4 py-3 text-left transition-colors ${selected === item.id ? 'bg-white shadow-sm' : 'hover:bg-white/70'}`}>
              <div className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${item.status === 'open' ? 'bg-green' : 'bg-navy/25'}`} /><p className="min-w-0 flex-1 truncate text-xs font-semibold text-navy">{labelFor(item.user_id)}</p><span className="text-[9px] text-navy/35">{dateTime(item.last_message_at)}</span></div>
              <p className="mt-1.5 line-clamp-2 text-[11px] leading-relaxed text-navy/55">{item.last_message?.body || 'Sin mensajes'}</p>
              <div className="mt-1.5 flex items-center justify-between text-[9px] text-navy/35"><span>{item.source_page || 'Ayuda general'}</span><span>{item.message_count} mensaje(s)</span></div>
            </button>
          ))}
        </aside>
        <section className="flex min-h-0 flex-col">
          {!detail ? <div className="flex flex-1 items-center justify-center text-sm text-navy/45">Selecciona una conversación.</div> : (
            <>
              <div className="flex items-center justify-between gap-3 border-b border-navy/10 px-4 py-3">
                <div className="min-w-0"><p className="truncate text-sm font-semibold text-navy">{labelFor(detail.user_id)}</p><p className="text-[10px] text-navy/45">Iniciada {dateTime(detail.created_at)} · {detail.source_page || 'Ayuda general'}</p></div>
                {detail.status === 'open' ? <button onClick={() => void close()} className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-coral/30 px-3 py-1.5 text-[11px] font-semibold text-coral hover:bg-coral/5"><XCircle className="h-3.5 w-3.5" /> Cerrar conversación</button> : <span className="rounded-full bg-navy/5 px-3 py-1 text-[10px] font-semibold text-navy/45">Cerrada</span>}
              </div>
              <div className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-slate-50/60 p-4">
                {detail.messages.map((item) => item.sender_role === 'system' ? <p key={item.id} className="mx-auto w-fit rounded-full bg-navy/5 px-3 py-1 text-[10px] text-navy/50">{item.body}</p> : (
                  <div key={item.id} className={`flex ${item.sender_role === 'admin' ? 'justify-end' : 'justify-start'}`}><div className={`max-w-[82%] rounded-xl px-3 py-2 text-xs leading-relaxed ${item.sender_role === 'admin' ? 'bg-teal text-white' : 'border border-navy/10 bg-white text-navy'}`}><span className="mb-1 flex items-center gap-1 text-[9px] font-semibold opacity-65">{item.sender_role === 'admin' ? <Headphones className="h-3 w-3" /> : <UserRound className="h-3 w-3" />}{item.sender_role === 'admin' ? 'ADS Veris' : 'Cliente'} · {dateTime(item.created_at)}</span><p className="whitespace-pre-wrap break-words">{item.body}</p></div></div>
                ))}
                <div ref={bottomRef} />
              </div>
              <div className="border-t border-navy/10 p-3">
                <div className="flex items-end gap-2 rounded-xl border border-navy/15 px-3 py-2 focus-within:border-teal"><textarea value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send() } }} disabled={detail.status === 'closed'} rows={2} maxLength={4000} placeholder={detail.status === 'closed' ? 'Conversación cerrada' : 'Responder al cliente…'} className="max-h-28 flex-1 resize-none bg-transparent text-sm text-navy outline-none disabled:text-navy/30" /><button onClick={() => void send()} disabled={sending || detail.status === 'closed' || !message.trim()} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-teal text-white disabled:bg-navy/10 disabled:text-navy/30">{sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}</button></div>
              </div>
            </>
          )}
        </section>
      </div>
    </Card>
  )
}
