import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import Button from '../components/ui/Button'

type Mode = 'login' | 'register'

const inputClass =
  'w-full rounded-lg border border-navy/20 bg-white px-3.5 py-2.5 text-sm text-navy placeholder-navy/35 outline-none transition-colors focus:border-teal focus:ring-2 focus:ring-teal/20'

export default function Login() {
  const { session, configured, login, register } = useAuth()
  const navigate = useNavigate()

  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [company, setCompany] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (session) return <Navigate to="/" replace />

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setNotice(null)
    setSubmitting(true)
    try {
      if (mode === 'login') {
        const { error: err } = await login(email, password)
        if (err) setError(err)
        else navigate('/')
      } else {
        const { error: err } = await register({ email, password, fullName, company })
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
              <label className="mb-1.5 block text-sm font-medium text-navy">
                Contraseña
              </label>
              <input
                required
                type="password"
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Mínimo 6 caracteres"
                className={inputClass}
              />
            </div>

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
