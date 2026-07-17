import { useEffect, useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, Eye, EyeOff } from 'lucide-react'
import { translateAuthError, useAuth } from '../auth/AuthContext'
import { supabase } from '../lib/supabase'
import Button from '../components/ui/Button'
import { isValidPassword, PASSWORD_POLICY_MESSAGE } from '../auth/password'
import { buildPasswordRecoveryRedirect } from '../auth/recovery'

type Mode = 'login' | 'register'

const inputClass =
  'w-full rounded-lg border border-navy/20 bg-white px-3.5 py-2.5 text-sm text-navy placeholder-navy/35 outline-none transition-colors focus:border-teal focus:ring-2 focus:ring-teal/20'

/** Botón de ojo para mostrar/ocultar la contraseña: accesible por teclado,
 * con aria-label, no borra el valor y conserva el foco en el campo. */
function EyeToggle({ shown, onToggle }: { shown: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onMouseDown={(e) => e.preventDefault() /* no robar el foco del input */}
      onClick={onToggle}
      aria-label={shown ? 'Ocultar contraseña' : 'Mostrar contraseña'}
      aria-pressed={shown}
      className="absolute inset-y-0 right-0 flex items-center px-3 text-navy/40 transition-colors hover:text-navy"
    >
      {shown ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
    </button>
  )
}

export default function Login() {
  const { session, configured, login, register } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [fullName, setFullName] = useState('')
  const [company, setCompany] = useState('')
  const [country, setCountry] = useState('Chile')
  const [phone, setPhone] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(() => {
    const routeState = location.state as { notice?: unknown } | null
    return typeof routeState?.notice === 'string' ? routeState.notice : null
  })
  const [submitting, setSubmitting] = useState(false)
  const [recovering, setRecovering] = useState(false)

  // Limpia el state de la ruta para que el aviso no reaparezca al navegar
  // hacia atrás/adelante o refrescar (ej. tras restablecer la contraseña).
  useEffect(() => {
    if ((location.state as { notice?: string } | null)?.notice) {
      navigate(location.pathname, { replace: true, state: null })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Ticks verdes SOLO cuando la contraseña cumple la política Y ambas coinciden.
  const passwordOk = isValidPassword(password)
  const confirmOk = passwordOk && confirmPassword.length > 0 && confirmPassword === password
  const confirmMismatch = confirmPassword.length > 0 && confirmPassword !== password

  if (session) return <Navigate to="/" replace />

  // Fase 10 §15.3: recuperar contraseña — Supabase envía el enlace por correo.
  const handleForgotPassword = async () => {
    setError(null)
    setNotice(null)
    if (!email.trim()) {
      setError('Escribe tu correo arriba y vuelve a presionar "¿Olvidaste tu contraseña?".')
      return
    }
    if (!supabase) return
    setRecovering(true)
    try {
      const { error: err } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        redirectTo: buildPasswordRecoveryRedirect(window.location.origin),
      })
      // Fase 15: jamás el mensaje técnico crudo de Supabase en pantalla
      if (err) setError(translateAuthError(err.message))
      else setNotice('Te enviamos un enlace para restablecer tu contraseña. Revisa tu correo.')
    } finally {
      setRecovering(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setNotice(null)
    // Fase 13: contraseña reforzada al crear cuenta — mínimo 8 caracteres
    // con al menos una letra y un número.
    if (mode === 'register' && !isValidPassword(password)) {
      setError(PASSWORD_POLICY_MESSAGE)
      return
    }
    // Fase 14: el envío se bloquea si la confirmación no coincide.
    if (mode === 'register' && password !== confirmPassword) {
      setError('Las contraseñas no coinciden. Revísalas antes de continuar.')
      return
    }
    setSubmitting(true)
    try {
      if (mode === 'login') {
        const { error: err } = await login(email, password)
        if (err) setError(err)
        else navigate('/')
      } else {
        const { error: err } = await register({
          email,
          password,
          fullName,
          company,
          country,
          phone,
        })
        if (err) {
          setError(err)
        } else {
          setNotice(
            'Cuenta creada. Si tu proyecto exige confirmación por correo, revisa tu bandeja antes de ingresar.',
          )
          setMode('login')
        }
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Panel de marca */}
      <div className="hidden flex-col justify-between bg-navy p-12 text-white lg:flex lg:w-[45%]">
        <span className="text-2xl font-extrabold tracking-tight">
          ADS <span className="text-gold">Veris</span>
        </span>
        <div>
          <h1 className="text-3xl font-bold leading-snug">
            Tu analista de datos,
            <br />
            siempre disponible.
          </h1>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-white/70">
            Sube tus datos, nosotros los limpiamos, los ordenamos y te los
            explicamos con IA para que tomes mejores decisiones en tu PyME.
          </p>
        </div>
        <p className="text-xs text-white/40">
          © {new Date().getFullYear()} ADS Veris · Chile
        </p>
      </div>

      {/* Formulario */}
      <div className="flex flex-1 items-center justify-center bg-work p-6">
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <span className="text-2xl font-extrabold tracking-tight text-navy">
              ADS <span className="text-gold">Veris</span>
            </span>
          </div>

          <h2 className="text-2xl font-bold text-navy">
            {mode === 'login' ? 'Inicia sesión' : 'Crea tu cuenta'}
          </h2>
          <p className="mt-1 text-sm text-navy/60">
            {mode === 'login'
              ? 'Bienvenido de vuelta a tu plataforma de análisis.'
              : 'Empieza a entender tus datos en minutos.'}
          </p>

          {!configured && (
            <div className="mt-6 flex items-start gap-3 rounded-lg border border-gold/40 bg-gold/10 p-4 text-sm text-navy">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
              <p>
                Supabase no está configurado. Copia{' '}
                <code className="rounded bg-navy/10 px-1 text-xs">.env.example</code>{' '}
                como <code className="rounded bg-navy/10 px-1 text-xs">.env</code> y
                completa las variables para habilitar el acceso.
              </p>
            </div>
          )}

          {notice && (
            <div className="mt-6 flex items-start gap-3 rounded-lg border border-green/40 bg-green/10 p-4 text-sm text-navy">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green" />
              <p>{notice}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            {mode === 'register' && (
              <>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-navy">
                    Nombre completo
                  </label>
                  <input
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Ej: Ítalo Alonso"
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-navy">
                    Empresa
                  </label>
                  <input
                    required
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                    placeholder="Ej: Comercial del Sur SpA"
                    className={inputClass}
                  />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-navy">
                      Pais
                    </label>
                    <input
                      required
                      value={country}
                      onChange={(e) => setCountry(e.target.value)}
                      placeholder="Ej: Chile"
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-navy">
                      Telefono
                    </label>
                    <input
                      required
                      type="tel"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder="Ej: +56 9 1234 5678"
                      className={inputClass}
                    />
                  </div>
                </div>
              </>
            )}

            <div>
              <label className="mb-1.5 block text-sm font-medium text-navy">
                Correo electrónico
              </label>
              <input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="tucorreo@empresa.cl"
                className={inputClass}
              />
            </div>

            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label className="block text-sm font-medium text-navy">Contraseña</label>
                {mode === 'login' && (
                  <button
                    type="button"
                    onClick={() => void handleForgotPassword()}
                    disabled={recovering}
                    className="text-xs font-medium text-teal hover:underline disabled:cursor-wait disabled:opacity-60"
                  >
                    {recovering ? 'Enviando enlace...' : '¿Olvidaste tu contraseña?'}
                  </button>
                )}
              </div>
              <div className="relative">
                <input
                  required
                  type={showPassword ? 'text' : 'password'}
                  minLength={mode === 'register' ? 8 : 6}
                  autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === 'register' ? 'Mínimo 8 caracteres, letras y números' : 'Tu contraseña'}
                  className={`${inputClass} pr-16`}
                />
                {mode === 'register' && passwordOk && (
                  <CheckCircle2
                    aria-hidden
                    className="absolute inset-y-0 right-9 my-auto h-4 w-4 text-green"
                  />
                )}
                <EyeToggle shown={showPassword} onToggle={() => setShowPassword((v) => !v)} />
              </div>
            </div>

            {mode === 'register' && (
              <div>
                <label className="mb-1.5 block text-sm font-medium text-navy">
                  Confirmar contraseña
                </label>
                <div className="relative">
                  <input
                    required
                    type={showConfirm ? 'text' : 'password'}
                    minLength={8}
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repite tu contraseña"
                    aria-invalid={confirmMismatch}
                    aria-describedby="confirmacion-estado"
                    className={`${inputClass} pr-16 ${confirmMismatch ? '!border-coral' : confirmOk ? '!border-green/60' : ''}`}
                  />
                  {confirmOk && (
                    <CheckCircle2
                      aria-hidden
                      className="absolute inset-y-0 right-9 my-auto h-4 w-4 text-green"
                    />
                  )}
                  <EyeToggle shown={showConfirm} onToggle={() => setShowConfirm((v) => !v)} />
                </div>
                {/* aria-live: el lector de pantalla anuncia el cambio de estado */}
                <p id="confirmacion-estado" aria-live="polite" className="mt-1 min-h-4 text-xs">
                  {confirmOk ? (
                    <span className="text-green">Las contraseñas coinciden.</span>
                  ) : confirmMismatch ? (
                    <span className="text-coral">Las contraseñas no coinciden.</span>
                  ) : null}
                </p>
              </div>
            )}

            {error && (
              <div className="flex items-start gap-2 rounded-lg border border-coral/40 bg-coral/10 p-3 text-sm text-coral">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <p>{error}</p>
              </div>
            )}

            <Button
              type="submit"
              disabled={submitting || !configured}
              className="w-full"
            >
              {submitting
                ? 'Un momento...'
                : mode === 'login'
                  ? 'Ingresar'
                  : 'Crear cuenta'}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-navy/60">
            {mode === 'login' ? '¿No tienes cuenta?' : '¿Ya tienes cuenta?'}{' '}
            <button
              onClick={() => {
                setMode(mode === 'login' ? 'register' : 'login')
                setError(null)
                setNotice(null)
                setConfirmPassword('')
                setShowPassword(false)
                setShowConfirm(false)
              }}
              className="font-semibold text-teal hover:underline"
            >
              {mode === 'login' ? 'Regístrate' : 'Inicia sesión'}
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
