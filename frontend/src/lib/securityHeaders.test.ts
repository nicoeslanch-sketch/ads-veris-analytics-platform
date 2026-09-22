import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('production browser security policy', () => {
  const config = JSON.parse(readFileSync(resolve(process.cwd(), 'vercel.json'), 'utf8'))
  const headers = Object.fromEntries(config.headers[0].headers.map((h: { key: string; value: string }) => [h.key, h.value]))
  const csp = headers['Content-Security-Policy'] as string

  it('forbids embedding and active objects, without allowing arbitrary scripts', () => {
    expect(headers['X-Frame-Options']).toBe('DENY')
    expect(headers['X-Content-Type-Options']).toBe('nosniff')
    expect(csp).toContain("frame-ancestors 'none'")
    expect(csp).toContain("object-src 'none'")
    expect(csp.split(';').find(d => d.trim().startsWith('script-src'))?.trim()).toBe("script-src 'self'")
  })

  it('allows the deployed API and auth, but no arbitrary connection origins', () => {
    const connect = csp.split(';').find(d => d.trim().startsWith('connect-src'))!
    expect(connect).toContain('https://ads-veris-api.onrender.com')
    expect(connect).toContain('https://tvxchffrpuqklyetpztw.supabase.co')
    expect(connect).not.toContain('*')
    expect(connect).not.toContain('http:')
  })
})
