/** RUT chileno — espejo EXACTO de api/app/rut.py (Fase 14).
 *
 * El frontend valida solo para dar feedback temprano (dígito verificador en
 * vivo); la autoridad es el backend + la RPC SQL. La normalización debe ser
 * idéntica en las tres capas: quitar puntos/espacios/guiones, K mayúscula,
 * canónico CUERPO-DV. El RUT jamás viaja en URLs ni queda en logs.
 */

const CLEAN_RE = /[.\s-]/g
const CANONICAL_RE = /^(\d{1,9})-([\dK])$/

export function normalizeRut(raw: string | null | undefined): string | null {
  if (!raw) return null
  const compact = raw.trim().replace(CLEAN_RE, '').toUpperCase()
  if (compact.length < 2 || compact.length > 10) return null
  const body = compact.slice(0, -1)
  const dv = compact.slice(-1)
  if (!/^\d+$/.test(body) || !/^[0-9K]$/.test(dv)) return null
  const trimmed = body.replace(/^0+/, '') || '0'
  if (trimmed === '0') return null
  return `${trimmed}-${dv}`
}

export function computeDv(body: string): string {
  let total = 0
  let factor = 2
  for (let i = body.length - 1; i >= 0; i--) {
    total += Number(body[i]) * factor
    factor = factor === 7 ? 2 : factor + 1
  }
  const remainder = 11 - (total % 11)
  if (remainder === 11) return '0'
  if (remainder === 10) return 'K'
  return String(remainder)
}

export function isValidRut(raw: string | null | undefined): boolean {
  const normalized = normalizeRut(raw)
  if (!normalized) return false
  const match = CANONICAL_RE.exec(normalized)
  if (!match) return false
  return computeDv(match[1]) === match[2]
}

/** '12345678-5' → '12.345.678-5' (solo para mostrar mientras se escribe). */
export function formatRut(normalized: string): string {
  const match = CANONICAL_RE.exec(normalized)
  if (!match) return normalized
  const body = match[1].replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return `${body}-${match[2]}`
}
