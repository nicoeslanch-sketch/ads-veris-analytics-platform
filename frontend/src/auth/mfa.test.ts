import { describe, expect, it } from 'vitest'
import { isTotpCode, mfaErrorMessage, parseSessionSecurity } from './mfa'

describe('MFA input and server status', () => {
  it.each([null, {}, [], { enforced: 'false' }])('rejects incomplete status %s', value => {
    expect(() => parseSessionSecurity(value)).toThrow()
  })
  it('accepts only the complete boolean contract', () => {
    const status = { enforced: true, has_mfa: true, admin_required: false, verified: false, needs_verification: true }
    expect(parseSessionSecurity(status)).toEqual(status)
  })
  it.each(['', '12345', '1234567', 'abcdef', '123 45', '１２３４５６'])('rejects invalid code %s', value => {
    expect(isTotpCode(value)).toBe(false)
  })
  it('preserves leading zeroes', () => { expect(isTotpCode('001234')).toBe(true) })
  it('does not expose raw provider diagnostics', () => {
    expect(mfaErrorMessage({ message: 'PRIVATE TOKEN', code: 'unexpected' })).not.toContain('PRIVATE TOKEN')
    expect(mfaErrorMessage({ code: 'mfa_verification_failed' })).toContain('incorrecto')
    expect(mfaErrorMessage({ code: 'over_request_rate_limit' })).toContain('Espera')
  })
})
