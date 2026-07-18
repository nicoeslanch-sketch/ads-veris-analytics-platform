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
import { Link } from 'react-router-dom'
import { ArrowUp, Crown, Loader2, Lock, RefreshCw, Sparkles, Square, Star, TriangleAlert } from 'lucide-react'
import { useDataset } from '../../data/DatasetContext'
import { useDemo } from '../../demo/DemoContext'
import { useAccess } from '../../lib/access'
import { ApiError, apiPost, apiPostJson, apiStream, buildDatasetForm } from '../../lib/api'
import { metricsCacheKey, requestMetrics } from '../../lib/analysisCache'
import { setActiveCurrency } from '../../lib/format'
import { serializedAnalysisScope } from '../../lib/multiSheet'
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

export default function AiPanel({ variant = 'panel' }: { variant?: 'panel' | 'drawer' } = {}) {
  // 'panel': columna fija de escritorio (xl+). 'drawer': cajón móvil.
  // El montaje lo decide AppShell — si este componente está montado, ES
  // visible, y solo entonces genera el resumen IA (Fase 10 §9.1: jamás
  // consumir cupo con el panel oculto).
  const asideClass =
    variant === 'drawer'
      ? 'flex h-full w-full flex-col bg-navy-deep text-white shadow-2xl'
      : 'flex h-full w-80 shrink-0 flex-col bg-navy-deep text-white'
  const {
    cleaning,
    metrics: contextMetrics,
    file,
    datasetId,
    storagePath,
    uploadedAt,
    mappingOverride,
    sheet,
    sheetManifest,
    analysisScope,
    eliminarDuplicados,
    setMetrics: setContextMetrics,
  } = useDataset()
  const active = Boolean(cleaning && file)
  // Fase 14: sin capacidad de IA (sin plan / prueba gratuita / expirada) el
  // panel muestra el mensaje comercial y NO llama a la API — ni una vez.
  const demo = useDemo()
  const { status: accessStatus, access, can } = useAccess()
  const aiBlocked = demo.active || accessStatus !== 'resolved' || !can('ask_data_ai')

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
  const activationRequest = useRef(0)
  const activationAbortRef = useRef<AbortController | null>(null)
  const streamAbortRef = useRef<AbortController | null>(null)
  // Métricas locales al panel (pueden venir del contexto o fetchearse aquí)
  const localMetrics = useRef<MetricsResult | null>(null)

  useEffect(() => {
    return () => {
      activationAbortRef.current?.abort()
      streamAbortRef.current?.abort()
    }
  }, [])

  // Auto-scroll al fondo cuando llegan mensajes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const runActivation = async (
    fileObj: File,
    storagePathArg: string | null,
    metricsArg: MetricsResult | null,
  ) => {
    activationAbortRef.current?.abort()
    const controller = new AbortController()
    activationAbortRef.current = controller
    const requestId = activationRequest.current + 1
    activationRequest.current = requestId
    const isCurrent = () => activationRequest.current === requestId && !controller.signal.aborted

    setLoading(true)
    setError(null)
    setSummary(null)
    setMessages([])
    localMetrics.current = null
    try {
      let m = metricsArg
      if (!m) {
        setLoadingLabel('Calculando indicadores…')
        const metricsKey = metricsCacheKey({
          dataset: datasetId ?? storagePathArg ?? String(uploadedAt?.getTime() ?? 0),
          sheet,
          analysisScope,
          mapping: mappingOverride,
          eliminarDuplicados,
          revision: cleaning?.revision,
          rules: cleaning?.reglas_activas,
          directed: cleaning?.dirigida,
          manifest: sheetManifest,
        })
        const serializedScope = serializedAnalysisScope(analysisScope)
        const fields: Record<string, string> = {
          eliminar_duplicados: String(eliminarDuplicados),
          ...(datasetId ? { dataset_id: datasetId } : {}),
          ...(mappingOverride ? { mapping: JSON.stringify(mappingOverride) } : {}),
          rules: JSON.stringify(cleaning?.reglas_activas ?? {}),
          ...(cleaning?.revision != null ? { revision: String(cleaning.revision) } : {}),
          ...(cleaning?.dirigida
            ? {
                scope: JSON.stringify({
                  incluir: cleaning.dirigida.columnas_incluir,
                  excluir: cleaning.dirigida.columnas_excluir,
                }),
              }
            : {}),
          ...(sheet ? { sheet } : {}),
          ...(sheetManifest && serializedScope
            ? {
                manifest: JSON.stringify(sheetManifest),
                analysis_scope: serializedScope,
              }
            : {}),
        }
        m = await requestMetrics(
          metricsKey,
          () => apiPost<MetricsResult>(
            '/metrics',
            buildDatasetForm(fileObj, storagePathArg, fields),
          ),
        )
        if (!isCurrent()) return
        setActiveCurrency(m.moneda)
        localMetrics.current = m
        setContextMetrics(m)
      } else {
        if (!isCurrent()) return
        localMetrics.current = m
      }
      if (m.moneda_mixta) {
        localMetrics.current = null
        setError(
          'La IA está bloqueada porque el archivo mezcla monedas incompatibles. Corrige ventas o costos en Limpieza.',
        )
        return
      }
      setLoadingLabel('Generando resumen con IA…')
      const res = await apiPostJson<Summary>('/ai/summary', { metrics: m }, {
        signal: controller.signal,
      })
      if (!isCurrent()) return
      setSummary(res)
    } catch (err) {
      if (!isCurrent()) return
      setError(err instanceof ApiError ? err.message : 'No se pudo iniciar el asistente.')
    } finally {
      if (activationAbortRef.current === controller) activationAbortRef.current = null
      if (isCurrent()) setLoading(false)
    }
  }

  // Disparar activación: una vez por archivo cuando cleaning esté listo
  useEffect(() => {
    if (!active || !file) {
      if (!active) {
        activationRequest.current += 1
        activationAbortRef.current?.abort()
        streamAbortRef.current?.abort()
        setSummary(null)
        setError(null)
        setMessages([])
        setLoading(false)
        localMetrics.current = null
        fetchedForFile.current = null
      }
      return
    }
    // Fase 14: bloqueado por plan/prueba (o acceso sin resolver) → cero llamadas.
    if (aiBlocked) return
    // uploadedAt distingue dos cargas distintas aunque el archivo se llame igual
    const fileKey = metricsCacheKey({
      dataset: datasetId ?? storagePath ?? String(uploadedAt?.getTime() ?? 0),
      sheet,
      analysisScope,
      mapping: mappingOverride,
      eliminarDuplicados,
      revision: cleaning?.revision,
      rules: cleaning?.reglas_activas,
      directed: cleaning?.dirigida,
      manifest: sheetManifest,
    })
    if (fetchedForFile.current === fileKey) return
    fetchedForFile.current = fileKey
    void runActivation(file, storagePath, contextMetrics)
    return () => {
      // Fase 12b: liberar la clave al desmontar (StrictMode/remontaje) — la
      // activación abortada quedaba "ya hecha" y el panel en spinner eterno.
      if (fetchedForFile.current === fileKey) fetchedForFile.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, aiBlocked, file, datasetId, storagePath, uploadedAt, sheet, sheetManifest, analysisScope, mappingOverride, eliminarDuplicados, cleaning])

  // Si las métricas llegan al contexto después (usuario visitó Resumen),
  // y el panel ya está activo con resumen, actualizar localMetrics silenciosamente.
  useEffect(() => {
    if (contextMetrics && active) localMetrics.current = contextMetrics
  }, [contextMetrics, active])

  const sendMessage = async (text: string) => {
    const m = localMetrics.current
    if (!text.trim() || streaming || !m || m.moneda_mixta) return
    const question = text.trim()
    setInput('')

    setMessages((prev) => [...prev, { role: 'user', content: question }])
    setMessages((prev) => [...prev, { role: 'assistant', content: '', streaming: true }])
    setStreaming(true)
    const controller = new AbortController()
    streamAbortRef.current = controller

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
        { signal: controller.signal },
      )
    } catch (err) {
      const msg = controller.signal.aborted
        ? 'Respuesta detenida.'
        : err instanceof ApiError
          ? err.message
          : 'Error al contactar el asistente.'
      setMessages((prev) => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last?.streaming) {
          updated[updated.length - 1] = {
            role: 'assistant',
            content: controller.signal.aborted ? msg : `⚠️ ${msg}`,
            streaming: false,
          }
        }
        return updated
      })
    } finally {
      if (streamAbortRef.current === controller) streamAbortRef.current = null
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

  const stopStreaming = () => {
    streamAbortRef.current?.abort()
  }

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void sendMessage(input)
    }
  }

  // ── Render: SIN CAPACIDAD DE IA (sin plan / prueba / expirada / demo) ─────
  // Fase 14: mensaje comercial claro y CERO llamadas a la API de IA.
  if (demo.active || (accessStatus === 'resolved' && !can('ask_data_ai'))) {
    const trial = access?.trial
    const detalle = demo.active
      ? 'En la demo el asistente está desactivado. Con un plan activo, aquí conversas con tus propios datos.'
      : trial?.active
        ? 'Tu prueba gratuita incluye estandarización, limpieza, dashboard y reportes — el asistente con IA se activa al contratar un plan.'
        : trial?.used
          ? 'Tu prueba gratuita terminó. Contrata un plan para analizar tus datos conversando con el asistente.'
          : 'Contrata un plan en la página Planes para analizar tus datos conversando con el asistente.'
    return (
      <aside className={asideClass}>
        <PanelHeader />
        <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gold/15">
            <Lock className="h-6 w-6 text-gold" />
          </div>
          <div>
            <p className="text-sm font-semibold text-white/90">
              El asistente con IA está disponible desde el Plan Básico
            </p>
            <p className="mt-2 text-xs leading-relaxed text-white/50">{detalle}</p>
          </div>
          {!demo.active && (
            <Link
              to="/planes"
              className="inline-flex items-center gap-2 rounded-lg bg-gold px-4 py-2 text-xs font-semibold text-navy-deep transition-colors hover:bg-gold/90"
            >
              <Crown className="h-3.5 w-3.5" /> Ir a Planes
            </Link>
          )}
        </div>
        <DisabledInput />
      </aside>
    )
  }

  // ── Render: BLOQUEADO ────────────────────────────────────────────────────
  if (!active) {
    return (
      <aside className={asideClass}>
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
      <aside className={asideClass}>
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
      <aside className={asideClass}>
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
    <aside className={asideClass}>
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
            type="button"
            onClick={streaming ? stopStreaming : () => void sendMessage(input)}
            disabled={!streaming && !input.trim()}
            title={streaming ? 'Detener respuesta' : 'Enviar'}
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-teal transition-colors hover:bg-teal/80 disabled:cursor-not-allowed disabled:bg-white/10"
          >
            {streaming ? (
              <Square className="h-2.5 w-2.5 fill-white text-white" />
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
