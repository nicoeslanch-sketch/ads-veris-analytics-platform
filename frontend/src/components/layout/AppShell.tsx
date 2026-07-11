import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Sparkles, X } from 'lucide-react'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import AiPanel from './AiPanel'
import DatasetBootstrap from './DatasetBootstrap'

/** Rutas donde vive el panel derecho del Asistente IA (Fase 7 §4):
 * SOLO Resumen y Explorar datos. En el resto, el contenido usa todo el ancho
 * (Limpieza tiene su propio chat horizontal de limpieza dirigida). */
const AI_PANEL_ROUTES = new Set(['/', '/explorar'])

/** ¿La media query está activa? (con suscripción a cambios). */
function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mql = window.matchMedia(query)
    const onChange = () => setMatches(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])
  return matches
}

/**
 * Layout fijo compartido por todas las pantallas (SPEC §4):
 * sidebar (navy) + topbar (navy) + área central (blanca) + panel IA (navy-deep).
 *
 * Fase 10 §9.1/§15.1 — responsive real:
 * - El sidebar es fijo en pantallas grandes y un cajón deslizante con
 *   hamburguesa en pantallas chicas.
 * - El panel IA SOLO se monta cuando es visible: en escritorio como columna,
 *   en pantallas menores como drawer que se abre con el botón flotante.
 *   Así jamás consume una consulta del cupo estando oculto.
 */
export default function AppShell() {
  const { pathname } = useLocation()
  const showAiPanel = AI_PANEL_ROUTES.has(pathname)
  const isDesktopAi = useMediaQuery('(min-width: 1280px)') // xl
  const isDesktopNav = useMediaQuery('(min-width: 1024px)') // lg

  const [navOpen, setNavOpen] = useState(false)
  const [aiOpen, setAiOpen] = useState(false)
  // Una vez abierto, el drawer queda montado (oculto con CSS): el resumen IA
  // se genera UNA vez y el historial del chat no se pierde al cerrarlo.
  const [aiEverOpened, setAiEverOpened] = useState(false)

  // Al navegar, cerrar los overlays móviles.
  useEffect(() => {
    setNavOpen(false)
    setAiOpen(false)
  }, [pathname])

  const openAi = () => {
    setAiEverOpened(true)
    setAiOpen(true)
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar fijo (≥lg) */}
      {isDesktopNav && <Sidebar />}

      {/* Sidebar móvil: cajón deslizante con fondo oscuro */}
      {!isDesktopNav && navOpen && (
        <div className="fixed inset-0 z-40 flex" onClick={() => setNavOpen(false)}>
          <div className="absolute inset-0 bg-navy-deep/60" />
          <div className="relative z-10 h-full" onClick={(e) => e.stopPropagation()}>
            <Sidebar onNavigate={() => setNavOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onMenuClick={!isDesktopNav ? () => setNavOpen(true) : undefined} />
        <div className="flex min-h-0 flex-1">
          <main className="min-w-0 flex-1 overflow-y-auto bg-work p-4 sm:p-6 lg:p-8">
            {/* Fase 11 §6: al iniciar sesión se retoma el último trabajo */}
            <DatasetBootstrap />
            <Outlet />
          </main>

          {/* Panel IA escritorio: solo montado cuando es visible */}
          {showAiPanel && isDesktopAi && <AiPanel />}
        </div>
      </div>

      {/* Panel IA en pantallas chicas: botón flotante + drawer */}
      {showAiPanel && !isDesktopAi && (
        <>
          {!aiOpen && (
            <button
              onClick={openAi}
              className="fixed bottom-5 right-5 z-40 flex h-13 w-13 items-center justify-center rounded-full bg-navy-deep p-3.5 text-gold shadow-lg ring-1 ring-gold/40 transition-transform hover:scale-105"
              aria-label="Abrir Asistente IA"
              title="Asistente IA"
            >
              <Sparkles className="h-6 w-6" />
            </button>
          )}
          {aiEverOpened && (
            <div
              className={`fixed inset-0 z-50 justify-end bg-navy-deep/60 ${aiOpen ? 'flex' : 'hidden'}`}
              onClick={() => setAiOpen(false)}
            >
              <div
                className="relative h-full w-full max-w-sm"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => setAiOpen(false)}
                  className="absolute right-3 top-4 z-10 rounded-lg p-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-white"
                  aria-label="Cerrar Asistente IA"
                >
                  <X className="h-5 w-5" />
                </button>
                <AiPanel variant="drawer" />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
