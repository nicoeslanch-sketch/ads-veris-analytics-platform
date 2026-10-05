import { useEffect, useState } from 'react'
import { Loader2, Send, Trash2 } from 'lucide-react'
import { ApiError, apiGet, apiPostJson } from '../lib/api'
import { LEGAL_VERSION, PRIVACY_EMAIL, PRIVACY_KINDS, PRIVACY_STATUSES, type PrivacyState } from '../lib/privacy'
import LegalConsent from './LegalConsent'

export default function PrivacyCenter() {
  const [data, setData] = useState<PrivacyState | null>(null)
  const [kind, setKind] = useState<keyof typeof PRIVACY_KINDS>('access')
  const [message, setMessage] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [receipt, setReceipt] = useState('')
  async function load() { setData(await apiGet<PrivacyState>('/privacy/account')) }
  useEffect(() => { let current = true
    apiGet<PrivacyState>('/privacy/account').then(result => { if (current) setData(result) })
      .catch(() => { if (current) setError('No pudimos cargar tus solicitudes. Puedes escribir al correo de privacidad.') })
    return () => { current = false }
  }, [])
  async function accept() {
    if (!consent || busy) return
    setBusy(true); setError('')
    try {
      const result = await apiPostJson<PrivacyState>('/privacy/acceptance', { version: LEGAL_VERSION, service_data_consent: true })
      setData(result)
    }
    catch (e) { setError(e instanceof ApiError ? e.message : 'No se pudo registrar la aceptacion.') }
    finally { setBusy(false) }
  }
  async function send() {
    if (!confirmed || busy) return
    setBusy(true); setError(''); setReceipt('')
    try {
      const result = await apiPostJson<{ id: string }>('/privacy/requests', { kind, message, confirmed: true })
      setReceipt(`Solicitud recibida. Comprobante: ${result.id}. Aun no se han eliminado datos.`)
      setMessage(''); setConfirmed(false)
      await load()
    } catch (e) { setError(e instanceof ApiError ? e.message : 'No se pudo registrar la solicitud. No confirmamos ningun borrado.') }
    finally { setBusy(false) }
  }
  return <section aria-label="Privacidad y datos" className="my-6 min-w-0 border-y border-navy/15 py-5">
    <h2 className="text-base font-semibold">Privacidad y datos</h2>
    <p className="mt-2 text-sm leading-relaxed text-navy/70">Responsable: ADS Veris SpA. <a href={`mailto:${PRIVACY_EMAIL}`} className="text-teal underline">{PRIVACY_EMAIL}</a></p>
    <div className="my-3 flex flex-wrap gap-4 text-sm text-teal"><a href="/privacidad" target="_blank" rel="noopener noreferrer">Politica de privacidad</a><a href="/condiciones" target="_blank" rel="noopener noreferrer">Condiciones</a><a href="/licencias" target="_blank" rel="noopener noreferrer">Licencias</a></div>
    {data && !data.accepted && <div className="mb-5 space-y-3">
      <LegalConsent checked={consent} onChange={setConsent} />
      <button onClick={() => void accept()} disabled={!consent || busy} className="text-sm font-semibold text-teal disabled:opacity-50">Registrar mi aceptacion</button>
    </div>}
    {data?.accepted && <p className="mb-4 text-xs text-navy/60">Aceptacion registrada: {data.version}.</p>}
    <h3 className="mb-2 text-sm font-semibold">Solicitudes sobre tus datos</h3>
    <p className="mb-3 text-sm leading-relaxed text-navy/70">El equipo de ADS Veris recibe estas solicitudes en su panel de administración y te responde aquí. No necesitas enviar una solicitud para ingresar o utilizar la plataforma.</p>
    <p className="mb-3 text-sm text-navy/70">Borra archivos concretos desde <a className="text-teal underline" href="/historial">Historial</a>. Para la cuenta completa, registra una solicitud. La eliminacion completa requiere revision y una confirmacion posterior; no es inmediata.</p>
    <form onSubmit={e => { e.preventDefault(); void send() }} className="max-w-2xl space-y-3">
      <label className="block text-sm">Tipo de solicitud<select value={kind} onChange={e => { setKind(e.target.value as typeof kind); setConfirmed(false) }} className="mt-1 block w-full rounded-lg border border-navy/20 bg-white p-2">
        {Object.entries(PRIVACY_KINDS).map(([key, title]) => <option key={key} value={key}>{title}</option>)}
      </select></label>
      <label className="block text-sm">Detalle (opcional)<textarea value={message} onChange={e => setMessage(e.target.value)} maxLength={2000} rows={3} className="mt-1 block w-full rounded-lg border border-navy/20 p-2" /></label>
      <p className="text-xs text-navy/60">No incluyas contrasenas, tarjetas ni documentos de identidad. Usaremos esta solicitud solo para atender tu derecho.</p>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" required checked={confirmed} onChange={e => setConfirmed(e.target.checked)} className="mt-1 shrink-0 accent-teal" />
        {kind === 'erasure' ? 'Solicito eliminar mi cuenta y mis datos. Entiendo que el borrado confirmado sera irreversible.' : 'Confirmo que esta solicitud corresponde a mis datos o a los que represento legalmente.'}</label>
      <button type="submit" disabled={!confirmed || busy} className="inline-flex items-center gap-2 rounded-lg border border-navy/20 px-3 py-2 text-sm font-medium disabled:opacity-50">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : kind === 'erasure' ? <Trash2 className="h-4 w-4" /> : <Send className="h-4 w-4" />}
        {kind === 'erasure' ? 'Solicitar eliminacion de cuenta y datos' : 'Enviar solicitud'}
      </button>
    </form>
    {error && <p role="alert" className="mt-3 text-sm text-coral">{error}</p>}
    {receipt && <p role="status" className="mt-3 break-words text-sm text-teal">{receipt}</p>}
    {!!data?.requests.length && <ul className="mt-5 divide-y divide-navy/10">{data.requests.map(r => <li key={r.id} className="min-w-0 py-3 text-sm">
      <p className="font-medium">{PRIVACY_KINDS[r.kind]} · {PRIVACY_STATUSES[r.status]}</p>
      <p className="mt-1 break-all text-xs text-navy/60">{r.id}</p>
      {r.response && <p className="mt-2 whitespace-pre-wrap break-words">{r.response}</p>}
    </li>)}</ul>}
  </section>
}
