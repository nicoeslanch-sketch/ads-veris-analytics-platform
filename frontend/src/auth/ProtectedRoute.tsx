import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from './AuthContext'

/**
 * Protege las rutas de la app: sin sesión activa redirige a /login.
 * Si Supabase no está configurado deja pasar para poder revisar el shell
 * en desarrollo (la sesión real exige variables de entorno).
 */
export default function ProtectedRoute() {
  const { session, loading, configured } = useAuth()

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-work">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-teal border-t-transparent" />
      </div>
    )
  }

  if (configured && !session) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
