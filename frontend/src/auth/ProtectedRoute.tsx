import { Navigate, Outlet } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { useAuth } from './AuthContext'
import LoadingSkeleton from '../components/ui/LoadingSkeleton'

/**
 * Protege las rutas de la app: sin sesión activa redirige a /login.
 *
 * Fase 10 §14.2 — sin Supabase configurado:
 * - En DESARROLLO deja pasar para poder revisar el shell.
 * - En PRODUCCIÓN una variable mal configurada NO debe abrir la app sin
 *   sesión: se muestra una pantalla de configuración inválida.
 */
export default function ProtectedRoute() {
  const { session, loading, configured } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen bg-work p-4 sm:p-8">
        <div aria-hidden="true" className="loading-skeleton mb-8 h-12 w-full" />
        <div className="mx-auto max-w-6xl"><LoadingSkeleton label="Comprobando tu sesión" /></div>
      </div>
    )
  }

  if (!configured && import.meta.env.PROD) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-work px-6 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-coral/10">
          <AlertTriangle className="h-7 w-7 text-coral" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-navy">Configuración incompleta</h1>
          <p className="mt-2 max-w-md text-sm text-navy/60">
            Faltan las variables VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY en el
            despliegue. Por seguridad, la plataforma no se abre sin autenticación
            configurada.
          </p>
        </div>
      </div>
    )
  }

  if (configured && !session) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
