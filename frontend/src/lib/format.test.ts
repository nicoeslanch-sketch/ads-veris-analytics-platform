import { describe, expect, it } from 'vitest'
import { cleanFilename, formatCLP, formatCurrencyCompact, formatNumber, formatRelativeTime, getActiveCurrency, setActiveCurrency } from './format'

describe('formatCLP', () => {
  it.each([NaN, Infinity, -Infinity])('no presenta %s como un KPI real', (value) => {
    expect(formatCLP(value)).toBe('\u2014')
    expect(formatNumber(value)).toBe('\u2014')
    expect(formatCurrencyCompact(value)).toBe('\u2014')
  })

  it('muestra UF cuando esa es la moneda activa', () => {
    setActiveCurrency('UF')
    expect(formatCLP(669700)).toBe('UF 669.700')
    expect(formatCLP(12.34)).toBe('UF 12,34')
    expect(formatCLP(0.004)).toBe('UF 0,004')
    expect(formatCurrencyCompact(0.004, 'UF')).toBe('UF 0,004')
    expect(formatCLP(1e-9)).toBe('<UF 0,00000001')
    expect(formatCurrencyCompact(-1e-9, 'UF')).toBe('>UF -0,00000001')
    setActiveCurrency('CLP')
  })

  it('mantiene pesos como moneda predeterminada', () => {
    setActiveCurrency(undefined)
    expect(formatCLP(669700)).toBe('$669.700')
  })

  it('conserva centavos de monedas extranjeras sin cambiar su unidad', () => {
    setActiveCurrency('USD')
    expect(formatCLP(12.34)).toBe('US$12,34')
    expect(formatCurrencyCompact(12.34, 'USD')).toBe('US$12,34')
    setActiveCurrency('EUR')
    expect(formatCLP(12.34)).toBe('\u20ac12,34')
    setActiveCurrency('CLP')
  })
})

describe('formatCurrencyCompact', () => {
  it.each([
    ['CLP', 26000000, '$26M'],
    ['USD', 26000000, 'US$26M'],
    ['UF', 12.34, 'UF 12,34'],
    ['EUR', -1500, '\u20ac-1,5K'],
    ['unknown', 2500, '$2,5K'],
  ])('usa %s sin heredar ni modificar la moneda global', (currency, value, expected) => {
    setActiveCurrency('USD')
    expect(formatCurrencyCompact(Number(value), String(currency))).toBe(expected)
    expect(getActiveCurrency()).toBe('USD')
    setActiveCurrency('CLP')
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
