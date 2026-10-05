export const LEGAL_VERSION = '2026-09-28'
export const PRIVACY_EMAIL = 'servicios@adsveris.com'
export const PRIVACY_CONTROLLER = 'ADS Veris SpA'
export const PRIVACY_CONTROLLER_RUT = '78.456.217-4'
export const PRIVACY_CONTROLLER_ADDRESS = 'Antonio Bellet 193, oficina 1210, Providencia'
export const LEGAL_IDENTITY_UPDATED_AT = '2026-10-04'
export const PRIVACY_KINDS = {
  access: 'Acceso y copia de mis datos',
  correction: 'Corregir mis datos',
  erasure: 'Eliminar mi cuenta y mis datos',
  objection: 'Revocar consentimiento u oponerme al tratamiento',
} as const
export const PRIVACY_STATUSES = {
  pending: 'Recibida', reviewing: 'En revision', resolved: 'Respondida', rejected: 'Rechazada con motivo',
} as const
export interface PrivacyRequest {
  id: string
  kind: keyof typeof PRIVACY_KINDS
  status: keyof typeof PRIVACY_STATUSES
  message: string
  response: string
  created_at: string
  updated_at: string
  email?: string
}
export interface PrivacyState { accepted: boolean; version: string; requests: PrivacyRequest[] }
