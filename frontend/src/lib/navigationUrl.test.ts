import { describe, expect, it } from 'vitest'
import { safeHttpsUrl } from './navigationUrl'

describe('navigation URL boundary', () => {
  it.each([
    'javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'java\nscript:alert(1)',
    'data:text/html,<script>alert(1)</script>', '//docs.google.com/test',
    '/local-path', 'http://docs.google.com/test', 'https://user:pass@docs.google.com/test',
    'https://docs.google.com\\@evil.example/test', '', null, {},
  ])('rejects script, relative, insecure or ambiguous URLs: %j', value => {
    expect(safeHttpsUrl(value)).toBeUndefined()
  })

  it('preserves signed HTTPS downloads without modifying their query', () => {
    const signed = 'https://storage.example/storage/v1/object/sign/report.csv?token=synthetic%2Btoken&download=report.csv'
    expect(safeHttpsUrl(signed)).toBe(signed)
  })

  it('requires the exact configured origin for Google links', () => {
    const origin = 'https://docs.google.com'
    expect(safeHttpsUrl(`${origin}/spreadsheets/d/example/edit#gid=0`, origin)).toBeDefined()
    for (const value of [
      'https://docs.google.com.evil.example/test', 'https://evil.example/docs.google.com',
      'https://docs.google.com:444/test', 'https://docs.google.com@evil.example/test',
    ]) expect(safeHttpsUrl(value, origin)).toBeUndefined()
  })
})
