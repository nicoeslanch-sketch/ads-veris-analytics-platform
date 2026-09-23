import { useEffect, useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronUp, Loader2, RefreshCw } from 'lucide-react'
import { apiGet } from '../../lib/api'

interface Health {
  sampled_at: string
  http: { instances: number; requests: number; errors: number; limited: number; slow: number }
  queue: { queued: number; running: number; max_active: number; oldest_wait_seconds: number }
  storage: { used_bytes: number; reserved_bytes: number; limit_bytes: number }
  alerts: { code: string; severity: 'critical' | 'warning'; title: string; detail: string }[]
}

const number = (value: number) => new Intl.NumberFormat('es-CL', { maximumFractionDigits: 1 }).format(value)

export default function OperationalHealth() {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<Health | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function refresh() {
      setLoading(true)
      try {
        const result = await apiGet<Health>('/admin/operations', { signal: controller.signal })
        if (!controller.signal.aborted) { setData(result); setError(false) }
      } catch {
        if (!controller.signal.aborted) { setError(true); setData(null) }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
          timer = setTimeout(() => void refresh(), 60_000)
        }
      }
    }
    void refresh()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [open, retry])
  const totals = data ? [
    ['Solicitudes (5 min)', number(data.http.requests)],
    ['Errores del servidor', number(data.http.errors)],
    ['Procesando / en cola', `${number(data.queue.running)} / ${number(data.queue.queued)}`],
    ['Espera mas antigua', `${number(data.queue.oldest_wait_seconds / 60)} min`],
    ['Almacenamiento y reservas', `${number((data.storage.used_bytes + data.storage.reserved_bytes) / 1048576)} / ${number(data.storage.limit_bytes / 1048576)} MiB`],
  ] : []
  return <section aria-label="Estado operativo" className="my-6 min-w-0 border-y border-navy/15 py-4">
    <button aria-expanded={open} onClick={() => setOpen(!open)}
      className="flex w-full items-center justify-between gap-3 text-left text-base font-semibold text-navy">
      Estado operativo {open ? <ChevronUp className="h-5 w-5 shrink-0" /> : <ChevronDown className="h-5 w-5 shrink-0" />}
    </button>
    {open && <div className="mt-4 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-navy/65">{data ? `Actualizado: ${new Date(data.sampled_at).toLocaleString('es-CL')}` : 'Sin lectura reciente'}</p>
        <button disabled={loading} title="Actualizar estado operativo" aria-label="Actualizar estado operativo"
          onClick={() => setRetry(value => value + 1)} className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-navy/20 disabled:opacity-50">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </button>
      </div>
      {error && <p role="alert" className="text-sm text-coral">No se pudo verificar el estado. Esto no confirma que la plataforma este funcionando correctamente.</p>}
      {data && <>
        <dl className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,11rem),1fr))] gap-x-5 gap-y-4">
          {totals.map(([label, value]) => <div key={label} className="min-w-0">
            <dt className="text-xs text-navy/60">{label}</dt>
            <dd className="mt-1 break-words text-sm font-semibold tabular-nums text-navy">{value}</dd>
          </div>)}
        </dl>
        {data.alerts.length ? <ul className="divide-y divide-navy/10">{data.alerts.map(alert => <li key={alert.code} className="flex min-w-0 gap-2 py-3">
          <AlertTriangle className={`mt-0.5 h-4 w-4 shrink-0 ${alert.severity === 'critical' ? 'text-coral' : 'text-amber-600'}`} />
          <div className="min-w-0"><p className="text-sm font-semibold text-navy">{alert.title}</p><p className="mt-1 break-words text-xs leading-relaxed text-navy/70">{alert.detail}</p></div>
        </li>)}</ul> : <p className="text-sm text-teal">Sin alertas en las mediciones disponibles.</p>}
      </>}
      <p className="text-xs text-navy/55">Avisos externos por correo pendientes de configurar. Un servidor detenido requiere supervision externa.</p>
    </div>}
  </section>
}
