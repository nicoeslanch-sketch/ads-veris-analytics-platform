export type PlanCode = 'basico' | 'gold' | 'analista'

export function isAnalystPlan(plan: PlanCode | string | null | undefined): boolean {
  return plan === 'gold' || plan === 'analista'
}

export function planLabel(plan: PlanCode | string | null | undefined): string {
  return isAnalystPlan(plan) ? 'Plan Analista' : 'Plan Básico'
}
