import { describe, expect, it } from 'vitest'
import {
  appendScope,
  basicMappingQuestions,
  joinScope,
  sheetStatusLabel,
  singleScope,
} from './multiSheet'
import type { DictionaryMatch } from './types'

const match = (rol: string, rolMotor: string | null, confidence = 1): DictionaryMatch => ({
  rol,
  grupo: 'test',
  tipo_dato: 'texto',
  rol_motor: rolMotor,
  palabra_clave: rol,
  metodo: 'exacto',
  confianza: confidence,
})

describe('mapeo simple del plan Basico', () => {
  it('pregunta unicamente por campos criticos faltantes o ambiguos', () => {
    expect(basicMappingQuestions(
      { fecha: 'Fecha', monto: 'Total' },
      { Fecha: match('fecha', 'fecha'), Total: match('monto', 'monto', 0.6) },
    )).toEqual(['monto'])
  })

  it('no expone TipoCliente como categoria de producto', () => {
    const questions = basicMappingQuestions(
      { fecha: 'Fecha', monto: 'Venta' },
      { TipoCliente: match('tipo_cliente', null) },
    )
    expect(questions).toEqual([])
  })

  it('avanza de una pregunta a la vez cuando una ya fue confirmada', () => {
    expect(basicMappingQuestions({}, {}, ['monto'])).toEqual(['fecha'])
  })
})

describe('estado multihoja', () => {
  it('distingue seleccion, progreso, error y limpieza', () => {
    expect(sheetStatusLabel(undefined, false, false)).toBe('No seleccionada')
    expect(sheetStatusLabel('estandarizando', true, false)).toBe('Procesando...')
    expect(sheetStatusLabel('error', true, false)).toBe('Error')
    expect(sheetStatusLabel('limpia', true, true)).toBe('Estandarizada y limpia')
  })

  it('construye alcances compartidos validos', () => {
    expect(singleScope('Ventas')).toEqual({ mode: 'single', sheets: ['Ventas'], active_sheet: 'Ventas' })
    expect(appendScope(['Enero', 'Febrero', 'Enero'])?.sheets).toEqual(['Enero', 'Febrero'])
    expect(appendScope(['Enero'])).toBeNull()
    expect(joinScope({
      left_sheet: 'Ventas',
      right_sheet: 'Productos',
      left_keys: ['ID'],
      right_keys: ['ID'],
      type: 'left',
    }).mode).toBe('join')
  })
})
