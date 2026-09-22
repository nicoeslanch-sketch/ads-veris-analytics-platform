export interface SessionSecurity {
  enforced: boolean
  has_mfa: boolean
  admin_required: boolean
  verified: boolean
  needs_verification: boolean
}

export function parseSessionSecurity(value: unknown): SessionSecurity {
  if (!value || typeof value !== 'object') throw new Error('Estado de seguridad no disponible.')
  const fields = ['enforced', 'has_mfa', 'admin_required', 'verified', 'needs_verification'] as const
  for (const key of fields) {
    if (!(key in value) || typeof (value as Record<string, unknown>)[key] !== 'boolean') {
      throw new Error('Estado de seguridad no disponible.')
    }
  }
  return value as SessionSecurity
}

export function isTotpCode(code: string): boolean {
  return /^\d{6}$/.test(code)
}

export function normalizeMfaQr(qr: string): string {
  if (!qr.startsWith('data:image/svg+xml;utf-8,') && !qr.startsWith('data:image/svg+xml,')) {
    throw new Error('Invalid authenticator QR')
  }
  const comma = qr.indexOf(',')
  const svg = qr.slice(comma + 1)
  // Supabase JS prefixes raw SVG: encode fragments such as fill="#000" too.
  return qr.slice(0, comma + 1) + (svg.trimStart().startsWith('<') ? encodeURIComponent(svg) : svg)
}

export function mfaErrorMessage(error: unknown): string {
  const code = error && typeof error === 'object' && 'code' in error ? String(error.code) : ''
  if (code.includes('rate_limit')) return 'Demasiados intentos. Espera un minuto antes de reintentar.'
  if (code === 'mfa_verification_failed' || code === 'mfa_challenge_expired') {
    return 'Codigo incorrecto o vencido. Usa el codigo actual de tu autenticador.'
  }
  return 'No se pudo completar la verificacion. Revisa tu conexion y vuelve a intentar.'
}
