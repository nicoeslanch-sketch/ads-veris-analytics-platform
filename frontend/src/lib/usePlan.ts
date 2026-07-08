/** Plan del usuario y capacidades — hooks compartidos (Fase 7).
 *
 * `usePlan` lee `profiles.plan` (con caché por usuario para no repetir la
 * consulta en cada página) y `useCapability` combina la matriz de planes con
 * el interruptor PLAN_ENFORCEMENT.
 */

import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { fetchProfile } from './profile'
import {
  PLAN_ENFORCEMENT,
  capabilityUnlocked,
  normalizePlan,
  planHasCapability,
  type Capability,
  type PlanCode,
} from './plans'

let cachedUserId: string | null = null
let cachedPlan: PlanCode | null = null

export function usePlan(): { plan: PlanCode; loading: boolean } {
  const { user } = useAuth()
  const userId = user?.id ?? null
  const [plan, setPlan] = useState<PlanCode>(
    cachedUserId === userId && cachedPlan ? cachedPlan : 'basico',
  )
  const [loading, setLoading] = useState(cachedUserId !== userId || cachedPlan === null)

  useEffect(() => {
    let cancelled = false
    if (cachedUserId === userId && cachedPlan) {
      setPlan(cachedPlan)
      setLoading(false)
      return
    }
    setLoading(true)
    fetchProfile()
      .then((profile) => {
        if (cancelled) return
        const normalized = normalizePlan(profile?.plan)
        cachedUserId = userId
        cachedPlan = normalized
        setPlan(normalized)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [userId])

  return { plan, loading }
}

export interface CapabilityState {
  /** Desbloqueada ahora (con enforcement apagado, siempre true). */
  allowed: boolean
  /** El plan la incluye según la matriz (para badges informativos). */
  hasByPlan: boolean
  enforced: boolean
  plan: PlanCode
  loading: boolean
}

export function useCapability(cap: Capability): CapabilityState {
  const { plan, loading } = usePlan()
  return {
    allowed: capabilityUnlocked(plan, cap),
    hasByPlan: planHasCapability(plan, cap),
    enforced: PLAN_ENFORCEMENT,
    plan,
    loading,
  }
}
