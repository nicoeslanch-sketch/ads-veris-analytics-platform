import { describe, expect, it } from 'vitest'
import {
  appendScope,
  basicMappingQuestions,
  cleaningScopeState,
  compatibleAppendSheets,
  joinScope,
  sheetPreparationAction,
  sheetSelectionCountLabel,
  sheetStatusLabel,
  sheetsForAutomaticPreparation,
  singleScope,
  standardizationScopeComplete,
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

  it('oculta resumen y preparacion redundantes cuando estan todas listas', () => {
    const sessions = {
      Enero: { standardization: { filas: 10 } },
      Febrero: { standardization: { filas: 12 } },
    }
    expect(sheetSelectionCountLabel('all', 2, 2)).toBeNull()
    expect(sheetPreparationAction(['Enero', 'Febrero'], sessions)).toBeNull()
  })

  it('distingue preparar por primera vez de actualizar una seleccion parcial', () => {
    expect(sheetPreparationAction(['Enero', 'Febrero'], {})).toBe('prepare')
    expect(sheetPreparationAction(
      ['Enero', 'Febrero'],
      { Enero: { standardization: { filas: 10 } } },
    )).toBe('update')
    expect(sheetSelectionCountLabel('custom', 1, 2)).toBe('1 de 2 hojas seleccionadas')
  })

  it('prepara automaticamente todas las hojas pendientes solo en modo todas', () => {
    const sessions = {
      Enero: { standardization: { filas: 10 }, status: 'estandarizada' },
      Febrero: { status: 'pendiente' },
      Productos: { status: 'error' },
    }
    const sheets = ['Enero', 'Febrero', 'Productos']

    expect(sheetsForAutomaticPreparation('all', sheets, sessions)).toEqual(['Febrero'])
    expect(sheetsForAutomaticPreparation('all', sheets, sessions, ['Enero'])).toEqual([])
    expect(sheetsForAutomaticPreparation('custom', sheets, sessions)).toEqual([])
  })

  it('bloquea el avance hasta terminar exactamente el alcance seleccionado', () => {
    const sessions = {
      Enero: { standardization: { filas: 10 }, cleaning: { filas: 10 } },
      Febrero: { standardization: { filas: 12 } },
    }
    expect(standardizationScopeComplete(['Enero', 'Febrero'], sessions)).toBe(true)
    expect(standardizationScopeComplete(['Enero', 'Marzo'], sessions)).toBe(false)
    expect(cleaningScopeState(['Enero', 'Febrero'], sessions)).toBe('partial')
    expect(cleaningScopeState(
      ['Enero', 'Febrero'],
      { ...sessions, Febrero: { ...sessions.Febrero, status: 'error' } },
    )).toBe('complete_with_errors')
    expect(cleaningScopeState(['Enero'], sessions, true)).toBe('cleaning')
  })

  it('no ofrece apilar hojas de distinta moneda aunque tengan las mismas columnas', () => {
    const result = (currency: string) => ({
      preview: { columnas: ['Fecha', 'Monto'] },
      column_types: { Fecha: 'fecha', Monto: 'numero' },
      mapeo: { fecha: 'Fecha', monto: 'Monto' },
      moneda: currency,
    })
    expect(compatibleAppendSheets(
      ['CLP', 'USD', 'CLP2'],
      { CLP: result('CLP'), USD: result('USD'), CLP2: result('CLP') },
    )).toEqual(['CLP', 'CLP2'])
  })
})
