import { Square } from 'lucide-react'
import { useEffect, useState } from 'react'
import { SkeletonLayout } from './ui/LoadingSkeleton'

export default function AnalysisLoadingPanel({
  operation,
  detail,
  onCancel,
  compact = false,
}: {
  operation: string
  detail: string
  onCancel?: () => void
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
      'min-w-0',
      compact ? 'py-3' : 'my-6 space-y-5',
    ].join(' ')}>
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <div role="status" aria-live="polite" aria-atomic="true">
            <p className="break-words text-sm font-semibold text-navy">{operation}</p>
            <p className="mt-1 break-words text-xs leading-relaxed text-navy/70">{detail}</p>
          </div>
          <p className="mt-2 text-[11px] font-medium text-teal">
            {seconds.toLocaleString('es-CL')} s transcurridos
          </p>
        </div>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-lg border border-navy/15 px-3 py-2 text-xs font-semibold text-navy/75 hover:bg-navy/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal focus-visible:ring-offset-2"
          >
            <Square className="h-3 w-3" aria-hidden="true" />
            Cancelar
          </button>
        )}
      </div>
      <div className="mt-5"><SkeletonLayout compact={compact} /></div>
      <div
        role="progressbar"
        aria-label={operation}
        className="mt-4 h-1.5 overflow-hidden rounded-full bg-navy/10"
      >
        <div className="h-full w-1/3 animate-[loading-slide_1.3s_ease-in-out_infinite] rounded-full bg-teal motion-reduce:animate-none" />
      </div>
    </div>
  )
}
