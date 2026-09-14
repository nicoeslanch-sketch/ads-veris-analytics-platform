import { useEffect, useState } from 'react'
import { HardDrive, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { apiGet } from '../lib/api'

type Quota = { used_bytes: number; reserved_bytes: number; limit_bytes: number; files: number; reserved_files: number; limit_files: number }
const mib = (bytes: number) => new Intl.NumberFormat('es-CL', { maximumFractionDigits: 1 }).format(bytes / 1024 / 1024)

export default function StorageUsage() {
  const [quota, setQuota] = useState<Quota | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let active = true
    setLoading(true)
    setError(false)
    apiGet<Quota>('/storage/quota').then((value) => { if (active) setQuota(value) })
      .catch(() => { if (active) setError(true) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [revision])
  return <section className="min-w-0 border-y border-navy/10 py-4 [overflow-wrap:anywhere]" aria-label="Almacenamiento de la cuenta">
    <div className="flex items-center justify-between gap-2">
      <h2 className="flex items-center gap-2 text-base font-semibold text-navy"><HardDrive className="h-4 w-4 shrink-0 text-teal" />Almacenamiento</h2>
      <button type="button" title="Actualizar cuota" aria-label="Actualizar cuota" disabled={loading} onClick={() => setRevision((value) => value + 1)} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md hover:bg-navy/5 disabled:opacity-40"><RefreshCw className={'h-4 w-4 ' + (loading ? 'animate-spin' : '')} /></button>
    </div>
    {loading ? <p className="mt-2 text-xs text-navy/60">Consultando cuota...</p> : error || !quota ? <p role="status" className="mt-2 text-xs text-coral">No se pudo consultar el espacio disponible.</p> : <>
      <p className="mt-2 text-sm text-navy">{mib(quota.used_bytes)} / {mib(quota.limit_bytes)} MiB</p>
      <progress aria-label="Espacio ocupado y reservado" value={quota.used_bytes + quota.reserved_bytes} max={quota.limit_bytes} className="mt-2 h-2 w-full accent-teal" />
      <p className="mt-2 text-xs text-navy/65">{quota.files} / {quota.limit_files} archivos originales</p>
      {quota.reserved_bytes > 0 && <p className="mt-1 text-xs text-navy/65">{mib(quota.reserved_bytes)} MiB reservados para escrituras pendientes.</p>}
      <Link to="/historial" className="mt-3 inline-block text-xs font-semibold text-teal">Gestionar archivos</Link>
    </>}
  </section>
}
