/** Plan del usuario y capacidades — hooks compartidos (Fase 7/8).
 *
 * Fase 14: ambos hooks son ahora ADAPTADORES sobre el AccessContext único
 * (lib/access.tsx → GET /me/access). Las capacidades vienen CALCULADAS del
 * servidor (plan + admin + prueba gratuita + enforcement): este archivo ya no
 * reconstruye nada desde la matriz local, y desapareció la carrera del
 * arranque optimista ('basico' mientras cargaba el perfil).
 */

import { useAccess } from './access'
import { normalizePlan, type Capability, type PlanCode } from './plans'

export function usePlan(): { plan: PlanCode; isAdmin: boolean; loading: boolean } {
  const { status, access } = useAccess()
  return {
    // Mientras carga (o en error) el plan reportado es 'sin_plan': ninguna
    // puerta del frontend debe abrirse con el acceso sin resolver. Las
    // acciones gated deben mirar también `loading` para no mostrar el modal
    // comercial por una carga lenta.
    plan: access ? normalizePlan(access.paid_plan) : 'sin_plan',
    isAdmin: Boolean(access?.is_admin),
    loading: status === 'loading',
  }
}

export interface CapabilityState {
  /** Desbloqueada ahora (servidor: admin/trial/enforcement ya considerados). */
  allowed: boolean
  /** Alias de allowed — se conserva por compatibilidad con badges antiguos. */
  hasByPlan: boolean
  enforced: boolean
  plan: PlanCode
  isAdmin: boolean
  loading: boolean
}

export function useCapability(cap: Capability): CapabilityState {
  const { status, access, can } = useAccess()
  return {
    allowed: can(cap),
    hasByPlan: can(cap),
    enforced: Boolean(access?.enforcement),
    plan: access ? normalizePlan(access.paid_plan) : 'sin_plan',
    isAdmin: Boolean(access?.is_admin),
    loading: status === 'loading',
  }
}
