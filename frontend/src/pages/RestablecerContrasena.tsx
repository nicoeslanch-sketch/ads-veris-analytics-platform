import { useEffect, useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
} from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { isValidPassword, PASSWORD_POLICY_MESSAGE } from '../auth/password'
import { getPasswordRecoveryError } from '../auth/recovery'
import Button from '../components/ui/Button'
import { supabase } from '../lib/supabase'

const inputClass =
  'w-full rounded-lg border border-navy/20 bg-white px-3.5 py-2.5 text-sm text-navy placeholder-navy/35 outline-none transition-colors focus:border-teal focus:ring-2 focus:ring-teal/20'

function EyeToggle({ shown, onToggle }: { shown: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onMouseDown={(event) => event.preventDefault()}
      onClick={onToggle}
      aria-label={shown ? 'Ocultar contraseña' : 'Mostrar contraseña'}
      aria-pressed={shown}
      className="absolute inset-y-0 right-0 flex items-center px-3 text-navy/40 transition-colors hover:text-navy"
    >
      {shown ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
    </button>
  )
}

export default function RestablecerContrasena() {
  const { session, loading, recoveryMode, configured, logout, clearRecoveryMode } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const linkError = getPasswordRecoveryError(location)

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [linkUnavailable, setLinkUnavailable] = useState(false)

  const passwordOk = isValidPassword(password)
  const confirmOk = passwordOk && confirmPassword.length > 0 && password === confirmPassword
  const confirmMismatch = confirmPassword.length > 0 && password !== confirmPassword
  const recoveryReady = Boolean(session && recoveryMode)

  useEffect(() => {
    if (!recoveryReady || (!location.hash && !location.search)) return
    window.history.replaceState(window.history.state, '', location.pathname)
  }, [location.hash, location.pathname, location.search, recoveryReady])

  useEffect(() => {
    if (recoveryReady || loading || linkError || !configured) return
    const timeout = window.setTimeout(() => setLinkUnavailable(true), 2000)
    return () => window.clearTimeout(timeout)
  }, [configured, linkError, loading, recoveryReady])

  const returnToLogin = () => {
    clearRecoveryMode()
    navigate('/login', { replace: true })
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)

    if (!isValidPassword(password)) {
      setError(PASSWORD_POLICY_MESSAGE)
      return
    }
    if (password !== confirmPassword) {
      setError('Las contraseñas no coinciden. Revísalas antes de continuar.')
      return
    }
    if (!supabase || !recoveryReady) {
      setError('El enlace ya no está disponible. Solicita uno nuevo.')
      return
    }

    setSubmitting(true)
    try {
      const { error: updateError } = await supabase.auth.updateUser({ password })
      if (updateError) {
        setError(
          updateError.message === 'New password should be different from the old password.'
            ? 'La nueva contraseña debe ser distinta de la anterior.'
            : updateError.message,
        )
        return
      }

      clearRecoveryMode()
      await logout()
      navigate('/login', {
        replace: true,
        state: { notice: 'Contraseña actualizada. Ya puedes iniciar sesión.' },
      })
    } finally {
      setSubmitting(false)
    }
  }

  if (!configured) {
    return <Navigate to="/login" replace />
  }

  const unavailable = Boolean(linkError) || linkUnavailable

  return (
    <div className="flex min-h-screen min-w-0 overflow-x-hidden bg-work">
      <div className="hidden flex-col justify-between bg-navy p-12 text-white lg:flex lg:w-[45%]">
        <span className="text-2xl font-extrabold tracking-tight">
          ADS <span className="text-gold">Veris</span>
        </span>
        <div>
          <h1 className="text-3xl font-bold leading-snug">Protege el acceso a tus datos.</h1>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-white/70">
            Define una nueva contraseña para volver a trabajar con tus análisis de forma segura.
          </p>
        </div>
        <p className="text-xs text-white/40">© {new Date().getFullYear()} ADS Veris · Chile</p>
      </div>

      <main className="flex min-w-0 flex-1 items-center justify-center p-6">
        <div className="min-w-0 w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <span className="text-2xl font-extrabold tracking-tight text-navy">
              ADS <span className="text-gold">Veris</span>
            </span>
          </div>

          <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-lg bg-teal/10 text-teal">
            <KeyRound className="h-6 w-6" />
          </div>
          <h1 className="break-words text-2xl font-bold text-navy">Crea una nueva contraseña</h1>
          <p className="mt-1 break-words text-sm leading-relaxed text-navy/60">
            Debe tener al menos 8 caracteres e incluir letras y números.
          </p>

          {unavailable ? (
            <div className="mt-6">
              <div className="flex items-start gap-3 rounded-lg border border-coral/40 bg-coral/10 p-4 text-sm text-coral">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <p className="min-w-0 break-words">
                  {linkError ?? 'El enlace de recuperación no es válido o ya venció.'}
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                className="mt-5 w-full whitespace-normal text-center"
                onClick={returnToLogin}
              >
                <ArrowLeft className="h-4 w-4" /> Volver para solicitar otro enlace
              </Button>
            </div>
          ) : !recoveryReady ? (
            <div className="mt-8 flex items-center gap-3 text-sm text-navy/60" aria-live="polite">
              <Loader2 className="h-5 w-5 animate-spin text-teal" /> Validando tu enlace seguro...
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-navy">Nueva contraseña</label>
                <div className="relative">
                  <input
                    required
                    type={showPassword ? 'text' : 'password'}
                    minLength={8}
                    autoComplete="new-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Mínimo 8 caracteres, letras y números"
                    className={`${inputClass} pr-16`}
                  />
                  {passwordOk && (
                    <CheckCircle2
                      aria-hidden
                      className="absolute inset-y-0 right-9 my-auto h-4 w-4 text-green"
                    />
                  )}
                  <EyeToggle shown={showPassword} onToggle={() => setShowPassword((value) => !value)} />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-navy">
                  Confirmar nueva contraseña
                </label>
                <div className="relative">
                  <input
                    required
                    type={showConfirm ? 'text' : 'password'}
                    minLength={8}
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    placeholder="Repite tu nueva contraseña"
                    aria-invalid={confirmMismatch}
                    aria-describedby="recuperacion-confirmacion"
                    className={`${inputClass} pr-16 ${confirmMismatch ? '!border-coral' : confirmOk ? '!border-green/60' : ''}`}
                  />
                  {confirmOk && (
                    <CheckCircle2
                      aria-hidden
                      className="absolute inset-y-0 right-9 my-auto h-4 w-4 text-green"
                    />
                  )}
                  <EyeToggle shown={showConfirm} onToggle={() => setShowConfirm((value) => !value)} />
                </div>
                <p id="recuperacion-confirmacion" aria-live="polite" className="mt-1 min-h-4 text-xs">
                  {confirmOk ? (
                    <span className="text-green">Las contraseñas coinciden.</span>
                  ) : confirmMismatch ? (
                    <span className="text-coral">Las contraseñas no coinciden.</span>
                  ) : null}
                </p>
              </div>

              {error && (
                <div className="flex items-start gap-2 rounded-lg border border-coral/40 bg-coral/10 p-3 text-sm text-coral">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <p>{error}</p>
                </div>
              )}

              <Button type="submit" disabled={submitting || !confirmOk} className="w-full">
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Guardando...
                  </>
                ) : (
                  'Cambiar contraseña'
                )}
              </Button>
            </form>
          )}
        </div>
      </main>
    </div>
  )
}
