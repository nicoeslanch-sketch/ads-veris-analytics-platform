import { describe, expect, it } from 'vitest'
import { cleanFilename, formatCLP, formatRelativeTime, setActiveCurrency } from './format'

describe('formatCLP', () => {
  it('muestra UF cuando esa es la moneda activa', () => {
    setActiveCurrency('UF')
    expect(formatCLP(669700)).toBe('UF 669.700')
    expect(formatCLP(12.34)).toBe('UF 12,34')
    setActiveCurrency('CLP')
  })

  it('mantiene pesos como moneda predeterminada', () => {
    setActiveCurrency(undefined)
    expect(formatCLP(669700)).toBe('$669.700')
  })
})

describe('cleanFilename', () => {
  it('quita el prefijo de timestamp que antepone Storage', () => {
    expect(cleanFilename('1783969608839_datos_prueba_adsveris.xlsx')).toBe(
      'datos_prueba_adsveris.xlsx',
    )
  })

  it('no toca nombres legítimos que empiezan con números cortos', () => {
    expect(cleanFilename('2026_ventas.csv')).toBe('2026_ventas.csv')
  })

  it('nombres ya limpios quedan intactos', () => {
    expect(cleanFilename('ventas.csv')).toBe('ventas.csv')
  })
})

describe('formatRelativeTime', () => {
  it('minutos', () => {
    expect(formatRelativeTime(new Date(Date.now() - 5 * 60_000))).toBe('hace 5 minutos')
  })

  it('horas', () => {
    expect(formatRelativeTime(new Date(Date.now() - 2 * 3_600_000))).toBe('hace 2 horas')
  })

  it('un minuto usa singular', () => {
    expect(formatRelativeTime(new Date(Date.now() - 60_000))).toBe('hace 1 minuto')
  })

  it('más de un mes cae a fecha absoluta', () => {
    const old = new Date(Date.now() - 40 * 86_400_000)
    const result = formatRelativeTime(old)
    expect(result).not.toContain('hace')
  })
})
