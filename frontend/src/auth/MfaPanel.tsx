import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Check, KeyRound, Loader2, Plus, RefreshCw, ShieldCheck, Trash2, X } from 'lucide-react'
import { supabase } from '../lib/supabase'
import { isTotpCode, mfaErrorMessage } from './mfa'

interface Factor { id: string; friendly_name?: string; status: string; factor_type: string }
interface Enrollment { id: string; qr: string; secret: string }
const button = 'inline-flex items-center justify-center gap-2 rounded-lg border border-navy/20 px-3 py-2 text-sm font-semibold disabled:opacity-50'

export default function MfaPanel({ required = false, admin = false, onVerified }: {
  required?: boolean; admin?: boolean; onVerified?: () => void
}) {
  const [factors, setFactors] = useState<Factor[]>([])
  const [selected, setSelected] = useState('')
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null)
  const [showSecret, setShowSecret] = useState(false)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(true)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [removing, setRemoving] = useState<string | null>(null)
  const busyRef = useRef(false)
  const verified = factors.filter(f => f.status === 'verified')
  const totp = verified.filter(f => f.factor_type === 'totp')

  async function load() {
    if (!supabase) throw new Error('Auth unavailable')
    const result = await supabase.auth.mfa.listFactors()
    if (result.error) throw result.error
    setFactors(result.data.all)
    const first = result.data.totp[0]?.id ?? ''
    setSelected(current => result.data.totp.some(f => f.id === current) ? current : first)
    setLoaded(true)
  }

  async function run(action: () => Promise<void>) {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setError('')
    try { await action() } catch (err) { setError(mfaErrorMessage(err)) }
    finally { busyRef.current = false; setBusy(false) }
  }

  useEffect(() => { void run(load) }, [])

  async function enroll() {
    if (!supabase) return
    const result = await supabase.auth.mfa.enroll({ factorType: 'totp', issuer: 'ADS Veris',
      friendlyName: `Autenticador ${new Date().toISOString()}` })
    if (result.error) throw result.error
    // Render provider SVG as an inert image, never as HTML. Keep secrets in memory only.
    const qr = result.data.totp.qr_code
    if (!qr.startsWith('data:image/svg+xml')) throw new Error('Invalid QR')
    setEnrollment({ id: result.data.id, qr, secret: result.data.totp.secret })
    setCode('')
    setNotice('')
  }

  async function verify(event: FormEvent) {
    event.preventDefault()
    if (!supabase || !isTotpCode(code) || !(enrollment?.id || selected)) return
    const client = supabase
    await run(async () => {
      const result = await client.auth.mfa.challengeAndVerify({ factorId: enrollment?.id || selected, code })
      setCode('')
      if (result.error) throw result.error
      setEnrollment(null)
      setShowSecret(false)
      setNotice('Segundo factor verificado.')
      await load()
      onVerified?.()
    })
  }

  async function remove(id: string) {
    if (!supabase) return
    const result = await supabase.auth.mfa.unenroll({ factorId: id })
    if (result.error) throw result.error
    setRemoving(null)
    if (enrollment?.id === id) { setEnrollment(null); setShowSecret(false); setCode('') }
    const refreshed = await supabase.auth.refreshSession()
    if (refreshed.error) throw refreshed.error
    await load()
  }

  return <section aria-label="Verificacion en dos pasos" className="min-w-0 space-y-4 text-navy">
    <h2 className="flex items-center gap-2 text-base font-semibold"><ShieldCheck className="h-5 w-5 shrink-0 text-teal" /> Verificacion en dos pasos</h2>
    {required && <p className="text-sm text-navy/70">{admin ? 'La cuenta administradora requiere un autenticador para continuar.' : 'Confirma tu identidad con tu autenticador.'}</p>}
    {error && <p role="alert" className="text-sm text-coral">{error}</p>}
    {notice && <p role="status" className="text-sm text-green">{notice}</p>}
    {busy && <p role="status" className="flex items-center gap-2 text-sm"><Loader2 className="h-4 w-4 animate-spin" /> Verificando...</p>}
    {loaded && !busy && !enrollment && !required && <p className="text-sm">{verified.length ? `${verified.length} autenticador(es) activo(s).` : 'Sin autenticador configurado.'}</p>}
    {enrollment && <div className="space-y-3">
      <p className="text-sm text-navy/70">Escanea el QR en tu aplicacion de autenticacion. No compartas el QR ni la clave.</p>
      <img src={enrollment.qr} alt="QR privado para configurar el autenticador" className="aspect-square w-52 max-w-full bg-white p-2" />
      <button type="button" onClick={() => setShowSecret(v => !v)} className={button}><KeyRound className="h-4 w-4" />{showSecret ? 'Ocultar clave' : 'Mostrar clave manual'}</button>
      {showSecret && <code className="block break-all text-sm select-all">{enrollment.secret}</code>}
    </div>}
    {(enrollment || (required && totp.length > 0)) && <form onSubmit={verify} className="space-y-3">
      {!enrollment && totp.length > 1 && <label className="block text-sm">Autenticador
        <select aria-label="Autenticador" value={selected} onChange={e => setSelected(e.target.value)} className="mt-1 block w-full min-w-0 rounded-lg border border-navy/20 p-2">{totp.map(f => <option key={f.id} value={f.id}>{f.friendly_name || 'Autenticador'}</option>)}</select>
      </label>}
      <label className="block text-sm">Codigo de seis digitos
        <input autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={code}
          onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          className="mt-1 block w-full rounded-lg border border-navy/20 px-3 py-2 text-base" />
      </label>
      <div className="flex flex-wrap gap-2"><button disabled={busy || !isTotpCode(code)} className={`${button} bg-teal text-white`}><Check className="h-4 w-4" /> Verificar codigo</button>
        {enrollment && <button type="button" disabled={busy} onClick={() => void run(() => remove(enrollment.id))} className={button}><X className="h-4 w-4" /> Cancelar configuracion</button>}
      </div>
    </form>}
    {!enrollment && (!required || verified.length === 0) && <button disabled={busy || !loaded} onClick={() => void run(enroll)} className={button}><Plus className="h-4 w-4" />{verified.length ? 'Agregar autenticador de respaldo' : 'Configurar autenticador'}</button>}
    {required && verified.length > 0 && !totp.length && <p className="text-sm text-coral">Esta cuenta no tiene un autenticador TOTP disponible. Revisa la recuperacion de acceso con soporte.</p>}
    {!enrollment && factors.filter(f => !required || f.status !== 'verified').map(f => <div key={f.id} className="flex min-w-0 flex-wrap items-center gap-2 border-t border-navy/10 pt-3">
      <span className="min-w-0 flex-1 break-words text-sm">{f.friendly_name || 'Autenticador'} · {f.status === 'verified' ? 'Activo' : 'Configuracion incompleta'}</span>
      <button disabled={busy || (admin && f.status === 'verified' && verified.length <= 1)} title={admin && verified.length <= 1 ? 'Agrega un autenticador de respaldo antes de retirar el ultimo.' : 'Retirar autenticador'} aria-label={`Retirar ${f.friendly_name || 'autenticador'}`} onClick={() => setRemoving(f.id)} className={`${button} h-9 w-9 p-0`}><Trash2 className="h-4 w-4" /></button>
      {removing === f.id && <div className="w-full space-y-2"><p className="text-sm">Este dispositivo dejara de servir para verificar tu acceso.</p><button disabled={busy} onClick={() => void run(() => remove(f.id))} className={button}>Confirmar retiro</button><button onClick={() => setRemoving(null)} className={`${button} ml-2`}>Cancelar</button></div>}
    </div>)}
    {error && <button disabled={busy} onClick={() => void run(load)} className={button}><RefreshCw className="h-4 w-4" /> Reintentar</button>}
    <p className="text-xs leading-relaxed text-navy/60">Conserva un autenticador de respaldo en otro dispositivo. Si pierdes el acceso, contacta a servicios@adsveris.com; nunca envies contrasenas, claves ni codigos.</p>
  </section>
}
