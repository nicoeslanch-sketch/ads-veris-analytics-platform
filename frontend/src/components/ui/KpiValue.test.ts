import { describe, expect, it } from 'vitest'
import { kpiFontSize } from './KpiValue'

/** Regresión: los montos largos de REQ5325 se partían a mitad del número
 * ("$1.113.784.6" + "43" en la línea siguiente). El valor nunca debe partirse:
 * la garantía estructural es `whitespace-nowrap`, y esta escala es la que
 * además lo hace caber sin recortarlo. */
describe('kpiFontSize', () => {
  it('mantiene el tamaño completo en valores cortos', () => {
    expect(kpiFontSize('$114.587'.length, 20)).toBe(20)
    expect(kpiFontSize('14.324'.length, 20)).toBe(20)
    expect(kpiFontSize('15,87%'.length, 20)).toBe(20)
  })

  it('reduce lo suficiente para que un monto de miles de millones quepa', () => {
    // 14 caracteres a ~0,6em por dígito deben caber en ~160px útiles.
    const size = kpiFontSize('$1.113.784.643'.length, 20)
    expect(size).toBeLessThan(20)
    expect('$1.113.784.643'.length * size * 0.6).toBeLessThanOrEqual(160)
  })

  it('nunca devuelve un tamaño ilegible', () => {
    const absurdo = kpiFontSize('$1.234.567.890.123.456'.length, 22)
    expect(absurdo).toBeGreaterThanOrEqual(13)
  })

  it('es monótona: más largo nunca es más grande', () => {
    const largos = [4, 8, 10, 12, 14, 16, 18, 22, 30]
    const tamanos = largos.map((largo) => kpiFontSize(largo, 22))
    tamanos.forEach((size, index) => {
      if (index > 0) expect(size).toBeLessThanOrEqual(tamanos[index - 1])
    })
  })
})
