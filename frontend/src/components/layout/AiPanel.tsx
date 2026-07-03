/**
 * Panel derecho del Asistente IA (SPEC §8).
 *
 * Estados:
 *  BLOQUEADO  — cleaning === null  → muestra candado, pide cargar datos
 *  CARGANDO   — cleaning activo, resumen pendiente → spinner + llama /ai/summary
 *  ACTIVO     → resumen auto, preguntas sugeridas, historial de chat, input
 */

import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Loader2, Lock, Sparkles, Star, TriangleAlert } from 'lucide-react'
import { useDataset } from '../../data/DatasetContext'
import { ApiError, apiPostJson, apiStream } from '../../lib/api'

// ── Tipos locales ─────────────────────────────────────────────────────────────

interface Message {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

interface Summary {
  resumen: string
  sugerencias: string[]
}

// ── Componente principal ──────────────────────────────────────────────────────

export default function AiPanel() {
  const { cleaning, metrics, file } = useDataset()
  const active = Boolean(cleaning && file)

  const [summary, setSummary] = useState<Summary | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)

  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fetchedForFile = useRef<string | null>(null)

  // Auto-scroll al fondo cuando llegan mensajes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Disparar resumen automático: una vez por archivo, cuando datos + métricas estén listos
  useEffect(() => {
    if (!active || !metrics || !file) {
      if (!active) {
        setSummary(null)
        setSummaryError(null)
        setMessages([])
        fetchedForFile.current = null
      }
      return
    }
    const fileKey = file.name
    if (fetchedForFile.current === fileKey) return
    fetchedForFile.current = fileKey

    setSummaryLoading(true)
    setSummaryError(null)
    apiPostJson<Summary>('/ai/summary', { metrics })
      .then((res) => setSummary(res))
      .catch((err) =>
        setSummaryError(err instanceof ApiError ? err.message : 'No se pudo generar el resumen.'),
      )
      .finally(() => setSummaryLoading(false))
  }, [active, metrics, file])

  const sendMessage = async (text: string) => {
    if (!text.trim() || streaming || !metrics) return
    const question = text.trim()
    setInput('')

    const userMsg: Message = { role: 'user', content: question }
    setMessages((prev) => [...prev, userMsg])

    // Mensaje de asistente vacío con flag streaming=true
    setMessages((prev) => [...prev, { role: 'assistant', content: '', streaming: true }])
    setStreaming(true)

    try {
      await apiStream(
        '/ai/chat',
        {
          pregunta: question,
          metrics,
          historial: messages.filter((m) => !m.streaming).map((m) => ({
            role: m.role,
            content: m.content,
          })),
        },
        (chunk) => {
          setMessages((prev) => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            if (last?.streaming) {
              updated[updated.length - 1] = {
                ...last,
                content: last.content + chunk,
              }
            }
            return updated
          })
        },
      )
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Error al contactar el asistente.'
      setMessages((prev) => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last?.streaming) {
          updated[updated.length - 1] = { role: 'assistant', content: `⚠️ ${msg}`, streaming: false }
        }
        return updated
      })
    } finally {
      // Marcar el último mensaje como completo (quitar flag streaming)
      setMessages((prev) => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last?.streaming) {
          updated[updated.length - 1] = { ...last, streaming: false }
        }
        return updated
      })
      setStreaming(false)
      inputRef.current?.focus()
    }
  }

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void sendMessage(input)
    }
  }

  // ── Render: BLOQUEADO ────────────────────────────────────────────────────
  if (!active) {
    return (
      <aside className="hidden h-full w-80 shrink-0 flex-col bg-navy-deep text-white xl:flex">
        <PanelHeader />
        <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-white/5">
            <Lock className="h-6 w-6 text-white/40" />
          </div>
          <div>
            <p className="text-sm font-semibold text-white/90">
              El asistente se activa cuando cargas tus datos
            </p>
            <p className="mt-2 text-xs leading-relaxed text-white/50">
              Sube y limpia tu primer archivo. Después, tu analista de datos con IA
              resumirá qué pasó en tu negocio, te sugerirá preguntas y responderá las tuyas.
            </p>
          </div>
        </div>
        <DisabledInput />
      </aside>
    )
  }

  // ── Render: CARGANDO resumen ─────────────────────────────────────────────
  if (summaryLoading || (!summary && !summaryError)) {
    return (
      <aside className="hidden h-full w-80 shrink-0 flex-col bg-navy-deep text-white xl:flex">
        <PanelHeader />
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
          <Loader2 className="h-7 w-7 animate-spin text-teal" />
          <p className="text-xs text-white/50">Analizando tu negocio…</p>
        </div>
        <DisabledInput />
      </aside>
    )
  }

  // ── Render: ACTIVO ───────────────────────────────────────────────────────
  return (
    <aside className="hidden h-full w-80 shrink-0 flex-col bg-navy-deep text-white xl:flex">
      <PanelHeader />

      {/* Cuerpo con scroll */}
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">

        {/* Resumen automático */}
        {summaryError ? (
          <div className="flex items-start gap-2 rounded-lg bg-coral/10 p-3 text-xs text-coral">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {summaryError}
          </div>
        ) : summary ? (
          <div className="rounded-xl bg-white/5 p-3">
            <div className="mb-2 flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-gold" />
              <span className="text-[10px] font-semibold uppercase tracking-wide text-gold">
                Resumen del periodo
              </span>
            </div>
            <p className="text-xs leading-relaxed text-white/80">{summary.resumen}</p>
          </div>
        ) : null}

        {/* Preguntas sugeridas (solo si no hay historial) */}
        {summary && messages.length === 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-white/40">
              Preguntas sugeridas
            </p>
            {summary.sugerencias.map((q) => (
              <button
                key={q}
                onClick={() => void sendMessage(q)}
                disabled={streaming}
                className="flex items-start gap-2 rounded-lg bg-white/5 px-3 py-2 text-left text-xs text-white/70 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Star className="mt-0.5 h-3 w-3 shrink-0 text-gold/70" />
                {q}
              </button>
            ))}
          </div>
        )}

        {/* Historial de mensajes */}
        {messages.map((msg, i) => (
          <ChatBubble key={i} msg={msg} />
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-white/10 p-3">
        <div className="flex items-end gap-2 rounded-lg bg-white/5 px-3 py-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder={streaming ? 'El asistente está respondiendo…' : 'Escribe tu pregunta…'}
            disabled={streaming}
            rows={1}
            className="max-h-24 min-h-[1.25rem] w-full resize-none bg-transparent text-sm text-white placeholder-white/30 outline-none"
            style={{ lineHeight: '1.25rem' }}
          />
          <button
            onClick={() => void sendMessage(input)}
            disabled={!input.trim() || streaming}
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-teal transition-colors hover:bg-teal/80 disabled:cursor-not-allowed disabled:bg-white/10"
          >
            {streaming ? (
              <Loader2 className="h-3 w-3 animate-spin text-white" />
            ) : (
              <ArrowUp className="h-3 w-3 text-white" />
            )}
          </button>
        </div>
        <p className="mt-1.5 text-center text-[10px] text-white/25">
          IA puede cometer errores. Verifica la información.
        </p>
      </div>
    </aside>
  )
}

// ── Sub-componentes ───────────────────────────────────────────────────────────

function PanelHeader() {
  return (
    <div className="flex h-16 items-center gap-2 border-b border-white/10 px-5">
      <Sparkles className="h-5 w-5 text-gold" />
      <h2 className="text-base font-semibold">Asistente IA</h2>
    </div>
  )
}

function DisabledInput() {
  return (
    <div className="border-t border-white/10 p-4">
      <div className="flex items-center gap-2 rounded-lg bg-white/5 px-3 py-2.5">
        <input
          disabled
          placeholder="Escribe tu pregunta…"
          className="w-full bg-transparent text-sm text-white/40 placeholder-white/30 outline-none"
        />
      </div>
      <p className="mt-2 text-center text-[10px] text-white/30">
        IA puede cometer errores. Verifica la información.
      </p>
    </div>
  )
}

function ChatBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[90%] rounded-xl px-3 py-2 text-xs leading-relaxed ${
          isUser
            ? 'bg-teal/20 text-white'
            : 'bg-white/5 text-white/85'
        }`}
      >
        {msg.content}
        {msg.streaming && (
          <span className="ml-1 inline-block h-3 w-px animate-pulse bg-white/60 align-middle" />
        )}
      </div>
    </div>
  )
}
