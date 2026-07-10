import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, Calendar, Check, ChevronDown, LogOut, Menu, Settings, User } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { ALL_PERIOD, monthPeriod, useDataset } from '../../data/DatasetContext'
import { formatMonthShort } from '../../lib/charts'

/** Rango por defecto: el mes actual, formateado es-CL (ej. "01 jun 2026 - 30 jun 2026"). */
function currentMonthRange(): string {
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth(), 1)
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0)
  const fmt = (d: Date) =>
    d.toLocaleDateString('es-CL', { day: '2-digit', month: 'short', year: 'numeric' })
  return `${fmt(start)} - ${fmt(end)}`
}

export default function Topbar({ onMenuClick }: { onMenuClick?: () => void } = {}) {
  const { user, logout } = useAuth()
  const { period, setPeriod, monthsAvailable } = useDataset()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [periodOpen, setPeriodOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const periodRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
      if (periodRef.current && !periodRef.current.contains(e.target as Node)) {
        setPeriodOpen(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const displayName =
    (user?.user_metadata?.full_name as string | undefined) ?? user?.email ?? 'Invitado'

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <header className="flex h-16 shrink-0 items-center justify-end gap-4 border-b border-white/10 bg-navy px-4 text-white sm:px-6">
      {/* Menú móvil (Fase 10 §15.1): abre el sidebar deslizante */}
      {onMenuClick && (
        <button
          onClick={onMenuClick}
          className="mr-auto rounded-lg p-2 text-white/80 transition-colors hover:bg-white/10"
          aria-label="Abrir menú"
        >
          <Menu className="h-5 w-5" />
        </button>
      )}
      {/* Selector de rango de fechas — filtra el dashboard (Fase 2) */}
      <div className="relative" ref={periodRef}>
        <button
          onClick={() => monthsAvailable.length > 0 && setPeriodOpen((v) => !v)}
          disabled={monthsAvailable.length === 0}
          className="flex items-center gap-2 rounded-lg border border-white/20 px-3.5 py-2 text-sm font-medium text-white/90 transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
          title={
            monthsAvailable.length === 0
              ? 'El filtro de fechas se habilita cuando cargas datos'
              : 'Filtrar por periodo'
          }
        >
          <Calendar className="h-4 w-4" />
          {monthsAvailable.length > 0 ? period.label : currentMonthRange()}
          <ChevronDown className="h-4 w-4 text-white/60" />
        </button>

        {periodOpen && (
          <div className="absolute right-0 top-12 z-20 w-56 overflow-hidden rounded-xl border border-navy/10 bg-white text-navy shadow-lg">
            {[ALL_PERIOD, ...monthsAvailable.map(monthPeriod)].map((option, index) => {
              const monthKey = index === 0 ? null : monthsAvailable[index - 1]
              const selected = option.label === period.label
              return (
                <button
                  key={option.label}
                  onClick={() => {
                    setPeriod(option)
                    setPeriodOpen(false)
                  }}
                  className={`flex w-full items-center justify-between px-4 py-2.5 text-sm hover:bg-navy/5 ${
                    selected ? 'font-semibold text-teal' : ''
                  }`}
                >
                  {monthKey ? formatMonthShort(monthKey) : option.label}
                  {selected && <Check className="h-4 w-4" />}
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Notificaciones */}
      <button
        className="relative rounded-full p-2 transition-colors hover:bg-white/10"
        title="Notificaciones"
      >
        <Bell className="h-5 w-5" />
      </button>

      {/* Menú de perfil */}
      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setMenuOpen((v) => !v)}
          className="flex items-center gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-white/10"
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-teal text-sm font-bold">
            {displayName.charAt(0).toUpperCase()}
          </span>
          <span className="max-w-40 truncate text-sm font-medium">{displayName}</span>
          <ChevronDown className="h-4 w-4 text-white/60" />
        </button>

        {menuOpen && (
          <div className="absolute right-0 top-12 z-20 w-52 overflow-hidden rounded-xl border border-navy/10 bg-white text-navy shadow-lg">
            <button
              onClick={() => {
                setMenuOpen(false)
                navigate('/configuracion')
              }}
              className="flex w-full items-center gap-2 px-4 py-2.5 text-sm hover:bg-navy/5"
            >
              <User className="h-4 w-4" /> Mi perfil
            </button>
            <button
              onClick={() => {
                setMenuOpen(false)
                navigate('/configuracion')
              }}
              className="flex w-full items-center gap-2 px-4 py-2.5 text-sm hover:bg-navy/5"
            >
              <Settings className="h-4 w-4" /> Configuración
            </button>
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-2 border-t border-navy/10 px-4 py-2.5 text-sm text-coral hover:bg-coral/5"
            >
              <LogOut className="h-4 w-4" /> Cerrar sesión
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
