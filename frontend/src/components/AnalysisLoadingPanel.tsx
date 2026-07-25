import { Loader2, Square } from 'lucide-react'
import { useEffect, useState } from 'react'

export default function AnalysisLoadingPanel({
  operation,
  detail,
  onCancel,
  compact = false,
}: {
  operation: string
  detail: string
  onCancel: () => void
  compact?: boolean
}) {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const started = Date.now()
    const timer = window.setInterval(() => {
      setSeconds(Math.floor((Date.now() - started) / 1000))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <div className={[
      'rounded-xl border border-teal/20 bg-white shadow-sm',
      compact ? 'p-4' : 'mx-auto my-10 max-w-2xl p-6',
    ].join(' ')}>
      <div className="flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-teal/10">
          <Loader2 className="h-5 w-5 animate-spin text-teal" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-navy">{operation}</p>
          <p className="mt-1 text-xs leading-relaxed text-navy/55">{detail}</p>
          <p className="mt-2 text-[11px] font-medium text-teal">
            {seconds.toLocaleString('es-CL')} s transcurridos
          </p>
        </div>
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-navy/15 px-3 py-2 text-xs font-semibold text-navy/65 hover:bg-navy/5"
        >
          <Square className="h-3 w-3" />
          Cancelar
        </button>
      </div>
      <div
        role="progressbar"
        aria-label={`${operation}. ${seconds} segundos transcurridos`}
        className="mt-4 h-1.5 overflow-hidden rounded-full bg-navy/10"
      >
        <div className="h-full w-1/3 animate-[loading-slide_1.3s_ease-in-out_infinite] rounded-full bg-gradient-to-r from-teal to-sky-500" />
      </div>
      <p className="mt-2 text-[10px] text-navy/40">
        El tiempo es real. No mostramos un porcentaje inventado mientras el servidor calcula.
      </p>
    </div>
  )
}
