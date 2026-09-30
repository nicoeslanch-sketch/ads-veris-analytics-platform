import { useCallback, useState, type ReactNode } from 'react'
import { LogOut } from 'lucide-react'
import { useAuth } from './AuthContext'
import PrivacyCenter from '../components/PrivacyCenter'

function AccountAcceptance({ children }: { children: ReactNode }) {
  const { logout } = useAuth()
  const [accepted, setAccepted] = useState(false)
  const onAccepted = useCallback(() => setAccepted(true), [])
  if (accepted) return <>{children}</>
  return <main className="min-h-screen bg-work px-5 py-8">
    <div className="mx-auto max-w-2xl">
      <h1 className="text-xl font-bold">Tu privacidad en ADS Veris</h1>
      <p className="mt-2 text-sm text-navy/70">Revisa las condiciones antes de continuar. Puedes ejercer tus derechos sin aceptarlas.</p>
      <PrivacyCenter onAccepted={onAccepted} />
      <button onClick={() => void logout()} className="inline-flex items-center gap-2 text-sm text-navy/70"><LogOut className="h-4 w-4" /> Cerrar sesion</button>
    </div>
  </main>
}

export default function PrivacyAcceptanceGate({ children }: { children: ReactNode }) {
  const { session } = useAuth()
  if (!session) return <>{children}</>
  return <AccountAcceptance key={session.user.id}>{children}</AccountAcceptance>
}
