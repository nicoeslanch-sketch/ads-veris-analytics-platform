import { useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronUp, Loader2, Trash2 } from 'lucide-react'
import { ApiError, apiGet, apiPostJson } from '../../lib/api'
import { PRIVACY_KINDS, PRIVACY_STATUSES, type PrivacyRequest } from '../../lib/privacy'

function RequestRow({ request, refresh }: { request: PrivacyRequest; refresh: () => Promise<void> }) {
  const [status, setStatus] = useState('reviewing')
  const [response, setResponse] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [eraseConfirmation, setEraseConfirmation] = useState('')
  async function save() {
    setBusy(true); setError('')
    try { await apiPostJson(`/privacy/admin/requests/${request.id}`, { status, response }); await refresh() }
    catch (e) { setError(e instanceof ApiError ? e.message : 'No se pudo guardar la respuesta.') }
    finally { setBusy(false) }
  }
  async function erase() {
    if (eraseConfirmation !== 'ELIMINAR CUENTA' || busy) return
    setBusy(true); setError('')
    try {
      await apiPostJson(`/privacy/admin/requests/${request.id}/erase`, {
        confirmation: 'ELIMINAR CUENTA',
      }, { timeoutMs: 240_000 })
      setEraseConfirmation('')
      await refresh()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo confirmar la eliminacion integral.')
    } finally { setBusy(false) }
  }
  return <li className="min-w-0 space-y-3 border-t border-navy/15 py-4 text-sm">
    <p className="font-medium">{PRIVACY_KINDS[request.kind]} · {PRIVACY_STATUSES[request.status]}</p>
    <p className="break-all text-xs text-navy/60">{request.email} · {request.id} · {new Date(request.created_at).toLocaleDateString('es-CL')}</p>
    {request.message && <p className="whitespace-pre-wrap break-words">{request.message}</p>}
    {request.response && <p className="whitespace-pre-wrap break-words">Respuesta: {request.response}</p>}
    {['pending', 'reviewing'].includes(request.status) && <form onSubmit={e => { e.preventDefault(); void save() }} className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <label>Estado<select className="mt-1 block w-full rounded-lg border border-navy/20 p-2" value={status} onChange={e => setStatus(e.target.value)}>
        <option value="reviewing">En revision</option><option value="resolved">Respondida</option><option value="rejected">Rechazada con motivo</option>
      </select></label>
      <label>Respuesta al titular<textarea required minLength={10} maxLength={2000} value={response} onChange={e => setResponse(e.target.value)} rows={3} className="mt-1 block w-full rounded-lg border border-navy/20 p-2" /></label>
      <p className="text-xs text-navy/65 sm:col-span-2">Cambiar el estado no borra datos. Para eliminacion, documenta la ejecucion y verificacion real, o el motivo y alcance de cualquier conservacion. No marques respondida una solicitud sin atenderla.</p>
      <button disabled={busy || response.trim().length < 10} className="inline-flex items-center justify-center gap-2 rounded-lg border border-navy/20 p-2 disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" />} Guardar respuesta</button>
    </form>}
    {request.kind === 'erasure' && ['pending', 'reviewing'].includes(request.status) && <div className="space-y-3 border-l-4 border-coral bg-coral/5 p-3">
      <p className="flex items-start gap-2 text-xs leading-relaxed"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-coral" />Esta accion bloquea la cuenta, elimina todos sus archivos, datos y acceso, y no se puede deshacer. Verifica antes la identidad y cualquier obligacion legal de conservacion.</p>
      <label className="block text-xs font-medium">Escribe ELIMINAR CUENTA para confirmar<input value={eraseConfirmation} onChange={e => setEraseConfirmation(e.target.value)} autoComplete="off" className="mt-1 block w-full max-w-sm border border-coral/50 bg-white p-2" /></label>
      <button type="button" onClick={() => void erase()} disabled={busy || eraseConfirmation !== 'ELIMINAR CUENTA'} className="inline-flex items-center justify-center gap-2 border border-coral px-3 py-2 text-sm font-semibold text-coral disabled:opacity-50"><Trash2 className="h-4 w-4" /> Ejecutar eliminacion integral</button>
    </div>}
    {error && <p role="alert" className="text-coral">{error}</p>}
  </li>
}
export default function PrivacyRequests() {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<PrivacyRequest[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function refresh() {
    setBusy(true); setError('')
    try { setItems(await apiGet<PrivacyRequest[]>('/privacy/admin/requests')) }
    catch { setError('No se pudo consultar la bandeja de privacidad.') }
    finally { setBusy(false) }
  }
  return <section aria-label="Solicitudes de privacidad" className="my-6 border-y border-navy/15 py-4">
    <button aria-expanded={open} onClick={() => { setOpen(!open); if (!open) void refresh() }} className="flex w-full items-center justify-between gap-3 text-left font-semibold">
      Solicitudes de privacidad {open ? <ChevronUp className="h-5 w-5 shrink-0" /> : <ChevronDown className="h-5 w-5 shrink-0" />}
    </button>
    {open && <div className="mt-4">
      {busy && <p role="status" className="text-sm">Consultando solicitudes...</p>}
      {error && <p role="alert" className="text-sm text-coral">{error}</p>}
      {!busy && !error && !items.length && <p className="text-sm text-navy/60">Sin solicitudes registradas.</p>}
      <ul>{items.map(r => <RequestRow key={r.id} request={r} refresh={refresh} />)}</ul>
    </div>}
  </section>
}
