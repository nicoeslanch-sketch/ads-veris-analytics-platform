/** Planes y capacidades — espejo frontend de `api/app/capabilities.py` (Fase 7).
 *
 * Matriz única de verdad para la UI: la página Planes, los candados de
 * Limpieza dirigida y Reportes, y las etiquetas de Configuración leen de aquí.
 * Si cambias algo, cámbialo también en el backend.
 *
 * PLAN_ENFORCEMENT (VITE_PLAN_ENFORCEMENT): con el flag apagado (Fase 7) todo
 * queda desbloqueado para probar, pero cada puerta ya tiene su cerradura.
 */

export type PlanCode = 'basico' | 'analista' | 'gold'

export type Capability =
  | 'standardize'
  | 'clean'
  | 'view_dashboard'
  | 'ask_data_ai'
  | 'download_clean_dataset'
  | 'download_reports'
  | 'ai_cleaning'
  | 'connect_sql'
  | 'community_access'

export const PLAN_ENFORCEMENT =
  ((import.meta.env.VITE_PLAN_ENFORCEMENT as string | undefined) ?? 'false') === 'true'

const BASICO: Capability[] = ['standardize', 'clean', 'view_dashboard', 'ask_data_ai']
const ANALISTA: Capability[] = [...BASICO, 'download_clean_dataset', 'download_reports', 'ai_cleaning']
const GOLD: Capability[] = [...ANALISTA, 'connect_sql', 'community_access']

export const PLAN_CAPABILITIES: Record<PlanCode, ReadonlySet<Capability>> = {
  basico: new Set(BASICO),
  analista: new Set(ANALISTA),
  gold: new Set(GOLD),
}

export function normalizePlan(plan: string | null | undefined): PlanCode {
  const value = (plan ?? 'basico').trim().toLowerCase()
  if (value === 'analista' || value === 'analyst') return 'analista'
  if (value === 'gold') return 'gold'
  return 'basico'
}

export function planHasCapability(plan: string | null | undefined, cap: Capability): boolean {
  return PLAN_CAPABILITIES[normalizePlan(plan)].has(cap)
}

/** ¿La función está desbloqueada AHORA? Con enforcement apagado, siempre. */
export function capabilityUnlocked(plan: string | null | undefined, cap: Capability): boolean {
  return !PLAN_ENFORCEMENT || planHasCapability(plan, cap)
}

export function planLabel(plan: string | null | undefined): string {
  const labels: Record<PlanCode, string> = {
    basico: 'Plan Básico',
    analista: 'Plan Analista',
    gold: 'Plan Gold',
  }
  return labels[normalizePlan(plan)]
}

/** Compatibilidad: Analista o superior (Gold hereda todo Analista). */
export function isAnalystPlan(plan: string | null | undefined): boolean {
  const normalized = normalizePlan(plan)
  return normalized === 'analista' || normalized === 'gold'
}

/* ── Metadata para la página Planes ── */

export type FeatureAvailability = 'si' | 'no' | 'construccion' | 'limitado'

export interface PlanFeatureRow {
  label: string
  availability: Record<PlanCode, FeatureAvailability>
}

/** Matriz de la página Planes (Fase 7 §1). */
export const PLAN_FEATURE_ROWS: PlanFeatureRow[] = [
  {
    label: 'Estandarizar y limpiar datos (reglas por defecto)',
    availability: { basico: 'si', analista: 'si', gold: 'si' },
  },
  {
    label: 'Dashboard, Explorar datos, Alertas e Historial',
    availability: { basico: 'si', analista: 'si', gold: 'si' },
  },
  {
    label: 'Asistente IA anclado a tus datos (insights)',
    availability: { basico: 'limitado', analista: 'si', gold: 'si' },
  },
  {
    label: 'Descargar la base de datos limpia (Excel / CSV)',
    availability: { basico: 'no', analista: 'si', gold: 'si' },
  },
  {
    label: 'Descargar reportes (PDF / Excel)',
    availability: { basico: 'no', analista: 'si', gold: 'si' },
  },
  {
    label: 'Chat de limpieza dirigida con tus variables (2/mes + tokens)',
    availability: { basico: 'no', analista: 'si', gold: 'si' },
  },
  {
    label: 'Conectar bases de datos SQL',
    availability: { basico: 'no', analista: 'no', gold: 'construccion' },
  },
  {
    label: 'Acceso a la comunidad ADS Veris',
    availability: { basico: 'no', analista: 'no', gold: 'construccion' },
  },
]

export interface PlanCard {
  code: PlanCode
  nombre: string
  tagline: string
  enConstruccion: boolean
  destacado: boolean
}

export const PLAN_CARDS: PlanCard[] = [
  {
    code: 'basico',
    nombre: 'Básico',
    tagline: 'Ordena y entiende tus datos: la plataforma hace el trabajo pesado.',
    enConstruccion: false,
    destacado: false,
  },
  {
    code: 'analista',
    nombre: 'Analista',
    tagline: 'Tu analista de datos siempre disponible: descarga tu base limpia y dirige la limpieza con tus variables.',
    enConstruccion: false,
    destacado: true,
  },
  {
    code: 'gold',
    nombre: 'Gold',
    tagline: 'Conecta tus bases SQL y únete a la comunidad ADS Veris.',
    enConstruccion: true,
    destacado: false,
  },
]
