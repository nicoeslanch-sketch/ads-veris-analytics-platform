import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import AiPanel from './AiPanel'

/** Rutas donde vive el panel derecho del Asistente IA (Fase 7 §4):
 * SOLO Resumen y Explorar datos. En el resto, el contenido usa todo el ancho
 * (Limpieza tiene su propio chat horizontal de limpieza dirigida). */
const AI_PANEL_ROUTES = new Set(['/', '/explorar'])

/**
 * Layout fijo compartido por todas las pantallas (SPEC §4):
 * sidebar (navy) + topbar (navy) + área central (blanca) + panel IA (navy-deep,
 * condicional por ruta desde la Fase 7).
 */
export default function AppShell() {
  const { pathname } = useLocation()
  const showAiPanel = AI_PANEL_ROUTES.has(pathname)
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <div className="flex min-h-0 flex-1">
          <main className="min-w-0 flex-1 overflow-y-auto bg-work p-8">
            <Outlet />
          </main>
          {showAiPanel && <AiPanel />}
        </div>
      </div>
    </div>
  )
}
