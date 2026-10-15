// Synthetic authentication used only by the isolated browser fixture.
import { createContext, useContext, useState, type ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'

const Auth = createContext<{ session: Session | null; logout: () => Promise<void> } | null>(null)
const sessionFor = (id: string, version = 0) => ({
  user: { id }, access_token: `synthetic-${id}-${version}`,
}) as Session

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => sessionFor('account-a'))
  const [version, setVersion] = useState(0)
  return <Auth.Provider value={{ session, logout: async () => setSession(null) }}>
    <nav>
      <button onClick={() => { setVersion(version + 1); setSession(sessionFor('account-a', version + 1)) }}>Renovar sesion de prueba</button>
      <button onClick={() => setSession(sessionFor('account-b'))}>Cambiar cuenta de prueba</button>
      <button onClick={() => setSession(null)}>Salir de prueba</button>
    </nav>
    {children}
  </Auth.Provider>
}

export function useAuth() {
  const value = useContext(Auth)!
  return { ...value, user: value.session?.user ?? null, recoveryMode: false, loading: false, configured: false }
}
