/** Plan del usuario y capacidades — hooks compartidos (Fase 7/8).
 *
 * `usePlan` lee `profiles.plan` + `profiles.is_admin` (con caché por usuario
 * para no repetir la consulta en cada página) y `useCapability` combina la
 * matriz de planes con el interruptor PLAN_ENFORCEMENT. La cuenta
 * administradora (Fase 8) tiene todas las capacidades sin depender del plan.
 */

import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { fetchProfile } from './profile'
import { supabaseConfigured } from './supabase'
import {
  PLAN_ENFORCEMENT,
  capabilityUnlocked,
  normalizePlan,
  planHasCapability,
  type Capability,
  type PlanCode,
} from './plans'

interface CachedFlags {
  plan: PlanCode
  isAdmin: boolean
}

let cachedUserId: string | null = null
let cachedFlags: CachedFlags | null = null

export function usePlan(): { plan: PlanCode; isAdmin: boolean; loading: boolean } {
  const { user } = useAuth()
  const userId = user?.id ?? null
  const [flags, setFlags] = useState<CachedFlags>(
    cachedUserId === userId && cachedFlags ? cachedFlags : { plan: 'basico', isAdmin: false },
  )
  const [loading, setLoading] = useState(cachedUserId !== userId || cachedFlags === null)

  useEffect(() => {
    let cancelled = false

    const refresh = () => {
      setLoading(true)
      fetchProfile()
        .then((profile) => {
          if (cancelled) return
          const next: CachedFlags = {
            plan: normalizePlan(profile?.plan),
            isAdmin: Boolean(profile?.is_admin),
          }
          cachedUserId = userId
          cachedFlags = next
          setFlags(next)
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }

    if (cachedUserId === userId && cachedFlags) {
      setFlags(cachedFlags)
      setLoading(false)
    } else {
      refresh()
    }

    // Fase 10 §11.3: si el administrador activa un plan mientras la sesión
    // está abierta, el usuario lo ve al volver a la pestaña (sin recargar).
    const onFocus = () => {
      cachedFlags = null
      refresh()
    }
    window.addEventListener('focus', onFocus)
    return () => {
      cancelled = true
      window.removeEventListener('focus', onFocus)
    }
  }, [userId])

  return { plan: flags.plan, isAdmin: flags.isAdmin, loading }
}

export interface CapabilityState {
  /** Desbloqueada ahora (admin siempre; con enforcement apagado, siempre). */
  allowed: boolean
  /** El plan la incluye según la matriz (para badges informativos). */
  hasByPlan: boolean
  enforced: boolean
  plan: PlanCode
  isAdmin: boolean
  loading: boolean
}

export function useCapability(cap: Capability): CapabilityState {
  const { plan, isAdmin, loading } = usePlan()
  // Sin Supabase (desarrollo local) no hay dónde mirar el plan: fail-open,
  // igual que el backend (capabilities.require_capability_for_user).
  const devOpen = !supabaseConfigured
  return {
    allowed: devOpen || isAdmin || capabilityUnlocked(plan, cap),
    hasByPlan: devOpen || isAdmin || planHasCapability(plan, cap),
    enforced: PLAN_ENFORCEMENT,
    plan,
    isAdmin,
    loading,
  }
}
