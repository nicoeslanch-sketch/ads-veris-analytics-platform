/** Contexto de acceso ÚNICO (Fase 14) — espejo cliente de GET /me/access.
 *
 * El servidor es la fuente de verdad para plan pagado, admin, estado de la
 * prueba gratuita y las capacidades EFECTIVAS: el frontend NO reconstruye
 * capacidades desde el plan (evita que las matrices Python/TS diverjan y
 * cierra la carrera del usePlan optimista que asumía 'basico' mientras
 * cargaba). Tres estados: 'loading' | 'resolved' | 'error' — sin acceso
 * optimista durante loading: las acciones con puerta esperan a 'resolved'.
 *
 * Tras activar la prueba o cambiar de plan: `applyAccess`/`refresh` actualizan
 * el contexto al instante, sin recargar la página.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useAuth } from '../auth/AuthContext'
import { apiGet } from './api'
import { supabaseConfigured } from './supabase'
import type { Capability } from './plans'

export interface TrialState {
  used: boolean
  active: boolean
  started_at: string | null
  ends_at: string | null
  days_remaining: number
}

export interface BillingIdentitySummary {
  id: string
  rut_type: 'empresa' | 'responsable'
  rut_masked: string
}

export interface AccessInfo {
  paid_plan: string
  plan_display: string
  is_admin: boolean
  enforcement: boolean
  trial: TrialState
  /** Identidad de facturación registrada (enmascarada) — la usa Planes al
   * contratar; null si el usuario aún no registra su RUT. */
  billing_identity?: BillingIdentitySummary | null
  capabilities: string[]
}

export type AccessStatus = 'loading' | 'resolved' | 'error'

export const EMPTY_TRIAL: TrialState = {
  used: false,
  active: false,
  started_at: null,
  ends_at: null,
  days_remaining: 0,
}

/** Desarrollo local sin Supabase: fail-open coherente con el backend. */
const DEV_OPEN_ACCESS: AccessInfo = {
  paid_plan: 'basico',
  plan_display: 'Básico',
  is_admin: false,
  enforcement: false,
  trial: EMPTY_TRIAL,
  capabilities: [
    'standardize',
    'clean',
    'view_dashboard',
    'ask_data_ai',
    'download_reports',
    'download_clean_dataset',
    'ai_cleaning',
    'connect_sql',
    'community_access',
  ],
}

interface AccessState {
  status: AccessStatus
  access: AccessInfo | null
  /** ¿La capacidad está desbloqueada AHORA? false mientras carga o en error
   * (fail-closed para acciones; la navegación no depende de esto). */
  can: (cap: Capability) => boolean
  refresh: () => void
  /** Aplica un AccessInfo recién recibido (ej: respuesta de POST /me/trial)
   * sin esperar otra vuelta a la red. */
  applyAccess: (access: AccessInfo) => void
}

const AccessContext = createContext<AccessState | undefined>(undefined)

// Caché por usuario a nivel de módulo: el provider vive en App, pero un
// remontaje (StrictMode, hot reload) no debe repetir la consulta.
let cachedUserId: string | null = null
let cachedAccess: AccessInfo | null = null

export function AccessProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const userId = user?.id ?? null
  const [state, setState] = useState<{ status: AccessStatus; access: AccessInfo | null }>(() => {
    if (!supabaseConfigured) return { status: 'resolved', access: DEV_OPEN_ACCESS }
    if (cachedUserId === userId && cachedAccess) {
      return { status: 'resolved', access: cachedAccess }
    }
    return { status: 'loading', access: null }
  })
  const requestSeq = useRef(0)

  const fetchAccess = useCallback(() => {
    if (!supabaseConfigured) {
      setState({ status: 'resolved', access: DEV_OPEN_ACCESS })
      return
    }
    if (!userId) {
      setState({ status: 'loading', access: null })
      return
    }
    const seq = requestSeq.current + 1
    requestSeq.current = seq
    // Fase 14b: "stale-while-revalidate" SOLO para el MISMO usuario — al
    // cambiar de cuenta en el mismo navegador, el acceso anterior se limpia
    // al instante (mantenerlo era mentirle a la UI con capacidades ajenas).
    setState((prev) => ({
      status: 'loading',
      access: cachedUserId === userId ? prev.access : null,
    }))
    apiGet<AccessInfo>('/me/access')
      .then((info) => {
        if (requestSeq.current !== seq) return
        cachedUserId = userId
        cachedAccess = info
        setState({ status: 'resolved', access: info })
      })
      .catch(() => {
        if (requestSeq.current !== seq) return
        // Fail-closed para acciones con puerta; el backend igual las protege.
        setState({ status: 'error', access: null })
      })
  }, [userId])

  useEffect(() => {
    if (!supabaseConfigured) return
    if (cachedUserId === userId && cachedAccess) {
      setState({ status: 'resolved', access: cachedAccess })
      return
    }
    // Usuario distinto al cacheado: nada del acceso anterior debe sobrevivir.
    if (cachedUserId !== userId) {
      cachedAccess = null
      setState({ status: 'loading', access: null })
    }
    fetchAccess()
  }, [userId, fetchAccess])

  // Si el administrador activa un plan (o la prueba expira) con la sesión
  // abierta, el usuario lo ve al volver a la pestaña — sin recargar.
  useEffect(() => {
    if (!supabaseConfigured) return
    const onFocus = () => {
      cachedAccess = null
      fetchAccess()
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [fetchAccess])

  const applyAccess = useCallback(
    (info: AccessInfo) => {
      cachedUserId = userId
      cachedAccess = info
      requestSeq.current += 1 // invalida respuestas en vuelo más antiguas
      setState({ status: 'resolved', access: info })
    },
    [userId],
  )

  const can = useCallback(
    (cap: Capability) => Boolean(state.access?.capabilities.includes(cap)),
    [state.access],
  )

  return (
    <AccessContext.Provider
      value={{ status: state.status, access: state.access, can, refresh: fetchAccess, applyAccess }}
    >
      {children}
    </AccessContext.Provider>
  )
}

export function useAccess(): AccessState {
  const ctx = useContext(AccessContext)
  if (!ctx) throw new Error('useAccess debe usarse dentro de <AccessProvider>')
  return ctx
}
