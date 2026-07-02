import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import AiPanel from './AiPanel'

/**
 * Layout fijo compartido por todas las pantallas (SPEC §4):
 * sidebar (navy) + topbar (navy) + área central (blanca) + panel IA (navy-deep).
 */
export default function AppShell() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <div className="flex min-h-0 flex-1">
          <main className="min-w-0 flex-1 overflow-y-auto bg-work p-8">
            <Outlet />
          </main>
          <AiPanel />
        </div>
      </div>
    </div>
  )
}
