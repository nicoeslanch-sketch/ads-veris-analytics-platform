/** Planes y capacidades — espejo frontend de `api/app/capabilities.py` (Fase 8).
 *
 * Matriz única de verdad para la UI: la página Planes, los candados de
 * Limpieza dirigida y descargas, y las etiquetas de Configuración leen de aquí.
 * Si cambias algo, cámbialo también en el backend.
 *
 * PLAN_ENFORCEMENT (VITE_PLAN_ENFORCEMENT): desde la Fase 8 queda ENCENDIDO
 * por defecto — descargar la base limpia y la limpieza dirigida exigen Plan
 * Analista; el reporte PDF del negocio es para todos. La cuenta administradora
 * (profiles.is_admin) pasa todas las puertas.
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
  ((import.meta.env.VITE_PLAN_ENFORCEMENT as string | undefined) ?? 'true') === 'true'

// Fase 8: download_reports pasa a Básico (el reporte PDF es para todos);
// lo que exige Analista es descargar la base LIMPIA (Excel/CSV).
const BASICO: Capability[] = ['standardize', 'clean', 'view_dashboard', 'ask_data_ai', 'download_reports']
const ANALISTA: Capability[] = [...BASICO, 'download_clean_dataset', 'ai_cleaning']
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

/** Matriz de la página Planes (Fase 8). */
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
    label: 'Reporte ejecutivo del negocio (PDF)',
    availability: { basico: 'si', analista: 'si', gold: 'si' },
  },
  {
    label: 'Descargar la base de datos limpia (Excel / CSV)',
    availability: { basico: 'no', analista: 'si', gold: 'si' },
  },
  {
    label: 'Limpieza dirigida con tus variables (10/mes Analista · 25/mes Gold + tokens)',
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

/* ── Costura para la pasarela de pago (Fase 9) ──
 * Hoy los planes se activan a mano: el usuario deja una solicitud
 * (POST /addons/request) y el administrador activa el plan desde
 * "Administrar cuentas". Cuando exista la pasarela (Webpay/Flow/MercadoPago),
 * reemplaza el cuerpo de startCheckout por la redirección al checkout;
 * el webhook de pago confirmado llamará a set_user_plan en el backend. */
export interface CheckoutResult {
  redirected: boolean
  mensaje: string
}

export function startCheckout(plan: PlanCode): CheckoutResult {
  // TODO pasarela de pago: redirigir al checkout del proveedor elegido.
  return {
    redirected: false,
    mensaje:
      plan === 'gold'
        ? 'El Plan Gold está en construcción: deja tu solicitud y te contactamos.'
        : 'Deja tu solicitud y activamos tu plan a la brevedad (pago manual mientras habilitamos el pago en línea).',
  }
}

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
