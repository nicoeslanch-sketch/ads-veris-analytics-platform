import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import type { Session, User } from '@supabase/supabase-js'
import { supabase, supabaseConfigured } from '../lib/supabase'
import { hasPasswordRecoveryHint } from './recovery'

interface RegisterData {
  email: string
  password: string
  fullName: string
  company: string
  country: string
  phone: string
}

interface AuthContextValue {
  session: Session | null
  user: User | null
  loading: boolean
  recoveryMode: boolean
  configured: boolean
  login: (email: string, password: string) => Promise<{ error: string | null }>
  register: (data: RegisterData) => Promise<{ error: string | null }>
  logout: () => Promise<void>
  clearRecoveryMode: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

/** Traduce los errores más comunes de Supabase Auth a es-CL. */
function translateAuthError(message: string): string {
  const map: Record<string, string> = {
    'Invalid login credentials': 'Correo o contraseña incorrectos.',
    'Email not confirmed': 'Debes confirmar tu correo antes de ingresar.',
    'User already registered': 'Ya existe una cuenta con este correo.',
    'Password should be at least 6 characters':
      'La contraseña debe tener al menos 6 caracteres.',
    'New password should be different from the old password.':
      'La contraseña nueva debe ser distinta de la anterior.',
    'Auth session missing!':
      'El enlace expiró o ya se usó. Solicita uno nuevo desde "¿Olvidaste tu contraseña?".',
  }
  return map[message] ?? message
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [recoveryMode, setRecoveryMode] = useState(() =>
    typeof window !== 'undefined' ? hasPasswordRecoveryHint(window.location) : false,
  )

  useEffect(() => {
    if (!supabase) {
      setLoading(false)
      return
    }
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, newSession) => {
      setSession(newSession)
      if (event === 'PASSWORD_RECOVERY') setRecoveryMode(true)
      if (event === 'SIGNED_OUT') setRecoveryMode(false)
    })
    return () => subscription.unsubscribe()
  }, [])

  const login: AuthContextValue['login'] = async (email, password) => {
    if (!supabase) return { error: 'Supabase no está configurado.' }
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    return { error: error ? translateAuthError(error.message) : null }
  }

  const register: AuthContextValue['register'] = async ({
    email,
    password,
    fullName,
    company,
    country,
    phone,
  }) => {
    if (!supabase) return { error: 'Supabase no está configurado.' }
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        // El trigger handle_new_user copia estos campos a public.profiles
        data: { full_name: fullName, company, country, phone },
      },
    })
    return { error: error ? translateAuthError(error.message) : null }
  }

  const logout = async () => {
    if (!supabase) return
    await supabase.auth.signOut()
  }

  const clearRecoveryMode = useCallback(() => setRecoveryMode(false), [])

  return (
    <AuthContext.Provider
      value={{
        session,
        user: session?.user ?? null,
        loading,
        recoveryMode,
        configured: supabaseConfigured,
        login,
        register,
        logout,
        clearRecoveryMode,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return ctx
}
