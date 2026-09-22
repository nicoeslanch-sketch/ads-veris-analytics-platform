import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Loader2, LogOut, RefreshCw } from 'lucide-react'
import { useAuth } from './AuthContext'
import { apiGet } from '../lib/api'
import MfaPanel from './MfaPanel'
import { parseSessionSecurity, type SessionSecurity } from './mfa'

export default function SecurityGate({ children }: { children: ReactNode }) {
  const { session, recoveryMode, logout } = useAuth()
  const userId = session?.user.id
  const [checkedUser, setCheckedUser] = useState<string>()
  const [checkedToken, setCheckedToken] = useState<string>()
  const [state, setState] = useState<SessionSecurity | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const retry = useCallback(() => setAttempt(n => n + 1), [])

  useEffect(() => {
    if (!userId || recoveryMode) return
    let cancelled = false
    const controller = new AbortController()
    setError('')
    apiGet<unknown>('/security/session', { timeoutMs: 60_000, signal: controller.signal })
      .then(parseSessionSecurity)
      .then(result => { if (!cancelled) { setState(result); setCheckedUser(userId); setCheckedToken(session?.access_token) } })
      .catch(() => { if (!cancelled) { setCheckedUser(undefined); setError('No pudimos verificar la seguridad de tu sesion. Tus datos permanecen protegidos.') } })
    return () => { cancelled = true; controller.abort() }
  }, [userId, session?.access_token, recoveryMode, attempt])

  useEffect(() => {
    const invalidate = () => { setCheckedUser(undefined); retry() }
    window.addEventListener('ads:mfa-required', invalidate)
    return () => window.removeEventListener('ads:mfa-required', invalidate)
  }, [retry])

  if (!session || recoveryMode) return <>{children}</>
  const checked = checkedUser === userId && checkedToken === session.access_token
  if (checked && state && !state.needs_verification) return <>{children}</>
  return <main className="min-h-screen bg-work px-4 py-10">
    <div className="mx-auto max-w-md space-y-5 rounded-lg border border-navy/15 bg-white p-5 shadow-sm">
      <h1 className="text-xl font-bold text-navy">ADS Veris</h1>
      {error ? <><p role="alert" className="text-sm text-coral">{error}</p><button onClick={retry} className="flex items-center gap-2 text-sm font-semibold text-teal"><RefreshCw className="h-4 w-4" /> Reintentar</button></>
        : !checked ? <p role="status" className="flex items-center gap-2 text-sm text-navy/70"><Loader2 className="h-4 w-4 animate-spin" /> Verificando acceso...</p>
        : <MfaPanel required admin={state?.admin_required} onVerified={retry} />}
      <button onClick={() => void logout()} className="inline-flex items-center gap-2 text-sm text-navy/70"><LogOut className="h-4 w-4" /> Cerrar sesion</button>
    </div>
  </main>
}
