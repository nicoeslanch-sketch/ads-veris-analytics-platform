/** Paridad del RUT con el backend (Fase 14b).
 *
 * MISMOS casos que api/tests/test_phase14.py — si una de las dos
 * implementaciones cambia sola, una de las dos suites falla. La normalización
 * debe ser idéntica en TS, Python y SQL.
 */
import { describe, expect, it } from 'vitest'
import { computeDv, formatRut, isValidRut, normalizeRut } from './rut'

describe('normalizeRut', () => {
  it('acepta formatos equivalentes', () => {
    expect(normalizeRut('12.345.678-k')).toBe('12345678-K')
    expect(normalizeRut('12345678K')).toBe('12345678-K')
    expect(normalizeRut('12 345 678 K')).toBe('12345678-K')
    expect(normalizeRut(' 012.345.678-K ')).toBe('12345678-K')
  })

  it('es idempotente', () => {
    for (const raw of ['12.345.678-k', '9.123.456-7', '76543210-0']) {
      const once = normalizeRut(raw)
      expect(once).not.toBeNull()
      expect(normalizeRut(once)).toBe(once)
    }
  })

  it('rechaza estructuras inválidas', () => {
    expect(normalizeRut('')).toBeNull()
    expect(normalizeRut(null)).toBeNull()
    expect(normalizeRut('ABC-K')).toBeNull()
    expect(normalizeRut('12.345.678-X')).toBeNull()
    expect(normalizeRut('0-0')).toBeNull()
    expect(normalizeRut('123456789012')).toBeNull()
  })
})

describe('módulo 11 (paridad con compute_dv de Python)', () => {
  it('calcula los DV conocidos', () => {
    expect(computeDv('12345678')).toBe('5')
    expect(computeDv('7654321')).toBe('6')
    expect(isValidRut('12.345.678-5')).toBe(true)
    expect(isValidRut('12.345.678-9')).toBe(false)
  })

  it('sin piso arbitrario de cuerpo (RUN antiguos son válidos)', () => {
    const body = '999999'
    expect(isValidRut(`${body}-${computeDv(body)}`)).toBe(true)
  })

  it('acepta patrones llamativos con DV válido', () => {
    expect(computeDv('11111111')).toBe('1')
    expect(isValidRut('11.111.111-1')).toBe(true)
  })
})

describe('formatRut', () => {
  it('agrega puntos para mostrar mientras se escribe', () => {
    expect(formatRut('12345678-5')).toBe('12.345.678-5')
    expect(formatRut('999999-K')).toBe('999.999-K')
  })
})
