import { useState } from 'react'
import { ChevronDown, ChevronUp, Loader2, RefreshCw } from 'lucide-react'
import { apiGet } from '../../lib/api'

interface Readiness {
  payment_activation_available: false
  items: { id: string; title: string; state: 'ready' | 'configured' | 'prepared' | 'deferred' | 'pending'; detail: string }[]
}
const labels = { ready: 'Verificado', configured: 'Configurado', prepared: 'Preparado', deferred: 'Pospuesto', pending: 'Pendiente' }

export default function CommercialReadiness() {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<Readiness | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  async function refresh() {
    setLoading(true); setError(false)
    try { setData(await apiGet<Readiness>('/admin/readiness')) }
    catch { setError(true); setData(null) }
    finally { setLoading(false) }
  }
  return <section aria-label="Preparacion comercial" className="my-6 min-w-0 border-y border-navy/15 py-4">
    <button aria-expanded={open} onClick={() => { setOpen(!open); if (!open && !data && !loading) void refresh() }}
      className="flex w-full items-center justify-between gap-3 text-left text-base font-semibold text-navy">
      Preparacion comercial {open ? <ChevronUp className="h-5 w-5 shrink-0" /> : <ChevronDown className="h-5 w-5 shrink-0" />}
    </button>
    {open && <div className="mt-4 space-y-3">
      <p className="text-sm text-navy/65">Cobros desactivados. La activacion de pagos todavia no esta disponible.</p>
      {error && <p role="alert" className="text-sm text-coral">No se pudo consultar el estado.</p>}
      <button disabled={loading} title="Actualizar preparacion comercial" aria-label="Actualizar preparacion comercial" onClick={() => void refresh()}
        className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-navy/20 disabled:opacity-50">
        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
      </button>
      {data && <ul className="divide-y divide-navy/10">{data.items.map(item => <li key={item.id} className="grid min-w-0 gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_7rem_minmax(0,2fr)]">
        <span className="break-words text-sm font-medium text-navy">{item.title}</span>
        <span className={`text-xs font-semibold ${item.state === 'ready' ? 'text-teal' : 'text-navy/65'}`}>{labels[item.state]}</span>
        <p className="min-w-0 break-words text-sm leading-relaxed text-navy/70">{item.detail}</p>
      </li>)}</ul>}
    </div>}
  </section>
}
