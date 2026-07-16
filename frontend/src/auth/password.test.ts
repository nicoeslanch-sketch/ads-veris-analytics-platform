import { describe, expect, it } from 'vitest'
import { isValidPassword } from './password'

describe('isValidPassword', () => {
  it('exige ocho caracteres, una letra y un número', () => {
    expect(isValidPassword('Clave123')).toBe(true)
    expect(isValidPassword('Segura2026!')).toBe(true)
  })

  it('rechaza contraseñas que no cumplen la política', () => {
    expect(isValidPassword('Clave12')).toBe(false)
    expect(isValidPassword('SoloLetras')).toBe(false)
    expect(isValidPassword('12345678')).toBe(false)
  })
})
