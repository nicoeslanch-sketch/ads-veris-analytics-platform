import { describe, expect, it } from 'vitest'
import { isTotpCode, mfaErrorMessage, normalizeMfaQr, parseSessionSecurity } from './mfa'

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
  it('encodes raw SVG fragments and rejects remote QR images', () => {
    const svg = '<svg><rect fill="#000"/></svg>'
    expect(normalizeMfaQr('data:image/svg+xml;utf-8,' + svg)).toBe('data:image/svg+xml;utf-8,' + encodeURIComponent(svg))
    expect(() => normalizeMfaQr('https://untrusted.invalid/qr')).toThrow()
    expect(() => normalizeMfaQr('data:text/html,<svg/>')).toThrow()
    const encoded = 'data:image/svg+xml,' + encodeURIComponent(svg)
    expect(normalizeMfaQr(encoded)).toBe(encoded)
  })
  it('does not expose raw provider diagnostics', () => {
    expect(mfaErrorMessage({ message: 'PRIVATE TOKEN', code: 'unexpected' })).not.toContain('PRIVATE TOKEN')
    expect(mfaErrorMessage({ code: 'mfa_verification_failed' })).toContain('incorrecto')
    expect(mfaErrorMessage({ code: 'over_request_rate_limit' })).toContain('Espera')
  })
})
