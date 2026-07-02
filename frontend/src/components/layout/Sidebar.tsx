import { NavLink } from 'react-router-dom'
import {
  Home,
  Search,
  Table2,
  Sparkles,
  History,
  Plug,
  Bell,
  FileText,
  FileSpreadsheet,
  Settings,
  HelpCircle,
  type LucideIcon,
} from 'lucide-react'
import { useDataset } from '../../data/DatasetContext'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
}

const navItems: NavItem[] = [
  { to: '/', label: 'Resumen', icon: Home },
  { to: '/explorar', label: 'Explorar datos', icon: Search },
  { to: '/estandarizacion', label: 'Estandarización', icon: Table2 },
  { to: '/limpieza', label: 'Limpieza de datos', icon: Sparkles },
  { to: '/historial', label: 'Historial', icon: History },
  { to: '/conectores', label: 'Conectores', icon: Plug },
  { to: '/alertas', label: 'Alertas', icon: Bell },
  { to: '/reportes', label: 'Reportes', icon: FileText },
  { to: '/configuracion', label: 'Configuración', icon: Settings },
]

export default function Sidebar() {
  const { file, cleaning } = useDataset()
  return (
    <aside className="flex h-full w-64 shrink-0 flex-col bg-navy text-white">
      {/* Logo */}
      <div className="flex h-16 items-center border-b border-white/10 px-6">
        <span className="text-xl font-extrabold tracking-tight">
          ADS <span className="text-gold">Veris</span>
        </span>
      </div>

      {/* Navegación */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-1">
          {navItems.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-white/10 text-white shadow-inner ring-1 ring-teal/60'
                      : 'text-white/70 hover:bg-white/5 hover:text-white'
                  }`
                }
              >
                <Icon className="h-4.5 w-4.5 shrink-0" />
                {label}
              </NavLink>
            </li>
          ))}
        </ul>

        {/* Fuentes conectadas */}
        <div className="mt-8 px-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-white/40">
            Fuentes conectadas
          </p>
          {file ? (
            <div className="mt-3 flex items-center gap-2.5 rounded-lg bg-white/5 px-3 py-2.5">
              <FileSpreadsheet className="h-4.5 w-4.5 shrink-0 text-green" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-white/90" title={file.name}>
                  Excel / CSV
                </p>
                <p className="truncate text-[10px] text-white/45">{file.name}</p>
              </div>
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${cleaning ? 'bg-green' : 'bg-gold'}`}
                title={cleaning ? 'Dataset limpio' : 'Pendiente de limpieza'}
              />
            </div>
          ) : (
            <p className="mt-3 text-xs text-white/50">
              Sin fuentes conectadas todavía. Carga tu primer archivo desde{' '}
              <NavLink to="/estandarizacion" className="text-teal hover:underline">
                Estandarización
              </NavLink>
              .
            </p>
          )}
        </div>
      </nav>

      {/* Bloque de ayuda */}
      <div className="border-t border-white/10 p-4">
        <div className="rounded-xl bg-navy-deep p-4">
          <div className="flex items-center gap-2">
            <HelpCircle className="h-4 w-4 text-gold" />
            <p className="text-sm font-semibold">¿Necesitas ayuda?</p>
          </div>
          <p className="mt-1 text-xs text-white/60">
            Revisa nuestra guía o contáctanos.
          </p>
          <button className="mt-3 w-full rounded-lg border border-gold/60 px-3 py-2 text-xs font-semibold text-gold transition-colors hover:bg-gold hover:text-navy-deep">
            Ir a ayuda
          </button>
        </div>
      </div>
    </aside>
  )
}
