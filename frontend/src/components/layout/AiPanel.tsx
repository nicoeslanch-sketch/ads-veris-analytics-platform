/**
 * Panel derecho del Asistente IA (SPEC §8).
 *
 * Estados:
 *  BLOQUEADO  — cleaning === null  → muestra candado, pide cargar datos
 *  CARGANDO   — cleaning activo, obtiene métricas + resumen → spinner
 *  ERROR      → mensaje de error con opción de reintentar
 *  ACTIVO     → resumen auto, preguntas sugeridas, historial de chat, input
 */

import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Loader2, Lock, RefreshCw, Sparkles, Star, TriangleAlert } from 'lucide-react'
import { useDataset } from '../../data/DatasetContext'
import { ApiError, apiPost, apiPostJson, apiStream, buildDatasetForm } from '../../lib/api'
import type { MetricsResult } from '../../lib/types'

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
  const {
    cleaning,
    metrics: contextMetrics,
    file,
    datasetId,
    storagePath,
    uploadedAt,
    mappingOverride,
    setMetrics: setContextMetrics,
  } = useDataset()
  const active = Boolean(cleaning && file)

  const [summary, setSummary] = useState<Summary | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingLabel, setLoadingLabel] = useState('Analizando tu negocio…')
  const [error, setError] = useState<string | null>(null)

  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)

  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fetchedForFile = useRef<string | null>(null)
  // Métricas locales al panel (pueden venir del contexto o fetchearse aquí)
  const localMetrics = useRef<MetricsResult | null>(null)

  // Auto-scroll al fondo cuando llegan mensajes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const runActivation = async (
    fileObj: File,
    storagePathArg: string | null,
    metricsArg: MetricsResult | null,
  ) => {
    setLoading(true)
    setError(null)
    try {
      let m = metricsArg
      if (!m) {
        setLoadingLabel('Calculando indicadores…')
        const fields: Record<string, string> = mappingOverride
          ? { mapping: JSON.stringify(mappingOverride) }
          : {}
        m = await apiPost<MetricsResult>('/metrics', buildDatasetForm(fileObj, storagePathArg, fields))
        localMetrics.current = m
        setContextMetrics(m)
      } else {
        localMetrics.current = m
      }
      setLoadingLabel('Generando resumen con IA…')
      const res = await apiPostJson<Summary>('/ai/summary', { metrics: m })
      setSummary(res)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo iniciar el asistente.')
    } finally {
      setLoading(false)
    }
  }

  // Disparar activación: una vez por archivo cuando cleaning esté listo
  useEffect(() => {
    if (!active || !file) {
      if (!active) {
        setSummary(null)
        setError(null)
        setMessages([])
        setLoading(false)
        localMetrics.current = null
        fetchedForFile.current = null
      }
      return
    }
    // uploadedAt distingue dos cargas distintas aunque el archivo se llame igual
    const fileKey = datasetId ?? storagePath ?? String(uploadedAt?.getTime() ?? 0)
    if (fetchedForFile.current === fileKey) return
    fetchedForFile.current = fileKey
    void runActivation(file, storagePath, contextMetrics)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, file, datasetId, storagePath, uploadedAt])

  // Si las métricas llegan al contexto después (usuario visitó Resumen),
  // y el panel ya está activo con resumen, actualizar localMetrics silenciosamente.
  useEffect(() => {
    if (contextMetrics && active) localMetrics.current = contextMetrics
  }, [contextMetrics, active])

  const sendMessage = async (text: string) => {
    const m = localMetrics.current
    if (!text.trim() || streaming || !m) return
    const question = text.trim()
    setInput('')

    setMessages((prev) => [...prev, { role: 'user', content: question }])
    setMessages((prev) => [...prev, { role: 'assistant', content: '', streaming: true }])
    setStreaming(true)

    try {
      await apiStream(
        '/ai/chat',
        {
          pregunta: question,
          metrics: m,
          historial: messages.filter((msg) => !msg.streaming).map((msg) => ({
            role: msg.role,
            content: msg.content,
          })),
        },
        (chunk) => {
          setMessages((prev) => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            if (last?.streaming) {
              updated[updated.length - 1] = { ...last, content: last.content + chunk }
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
      setMessages((prev) => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last?.streaming) updated[updated.length - 1] = { ...last, streaming: false }
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

  // ── Render: CARGANDO ─────────────────────────────────────────────────────
  if (loading) {
    return (
      <aside className="hidden h-full w-80 shrink-0 flex-col bg-navy-deep text-white xl:flex">
        <PanelHeader />
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
          <Loader2 className="h-7 w-7 animate-spin text-teal" />
          <p className="text-xs text-white/50">{loadingLabel}</p>
        </div>
        <DisabledInput />
      </aside>
    )
  }

  // ── Render: ERROR ────────────────────────────────────────────────────────
  if (error) {
    return (
      <aside className="hidden h-full w-80 shrink-0 flex-col bg-navy-deep text-white xl:flex">
        <PanelHeader />
        <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-coral/10">
            <TriangleAlert className="h-6 w-6 text-coral" />
          </div>
          <div>
            <p className="text-sm font-semibold text-white/90">Error al iniciar el asistente</p>
            <p className="mt-2 text-xs leading-relaxed text-coral/80">{error}</p>
          </div>
          <button
            onClick={() => {
              if (file) {
                fetchedForFile.current = null
                void runActivation(file, storagePath, contextMetrics)
              }
            }}
            className="flex items-center gap-2 rounded-lg bg-white/10 px-4 py-2 text-xs font-semibold text-white/80 transition-colors hover:bg-white/15"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Reintentar
          </button>
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
        {summary && (
          <div className="rounded-xl bg-white/5 p-3">
            <div className="mb-2 flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-gold" />
              <span className="text-[10px] font-semibold uppercase tracking-wide text-gold">
                Resumen del periodo
              </span>
            </div>
            <p className="text-xs leading-relaxed text-white/80">{summary.resumen}</p>
          </div>
        )}

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
          isUser ? 'bg-teal/20 text-white' : 'bg-white/5 text-white/85'
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
