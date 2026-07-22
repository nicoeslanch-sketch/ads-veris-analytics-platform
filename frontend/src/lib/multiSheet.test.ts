import { describe, expect, it } from 'vitest'
import {
  analysisScopesEqual,
  appendScope,
  automaticCleaningSignature,
  basicMappingQuestions,
  cleaningScopeState,
  compatibleAppendSheets,
  joinScope,
  sheetPreparationAction,
  sheetSelectionCountLabel,
  sheetStatusLabel,
  sheetsForAutomaticCleaning,
  sheetsForAutomaticPreparation,
  relationshipPlainMessage,
  requiresSalesAmountMapping,
  restoredAnalysisSelection,
  restoredSheetStatus,
  serializedAnalysisScope,
  selectAppendJoinCostCandidates,
  shouldAutoBuildBusinessScope,
  singleScope,
  standardizationScopeComplete,
  synchronizeAppendJoinSelection,
  updateBatchSheetErrors,
  withSheetSelection,
  withPublicAnalysisScope,
} from './multiSheet'
import type { AnalysisScope, DictionaryMatch, RelationshipCandidate } from './types'

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

  it('no pregunta por roles sin columnas candidatas (hoja no transaccional)', () => {
    // Una maestra de clientes sin fechas ni números no debe preguntar nada.
    expect(
      basicMappingQuestions({}, {}, [], { ID_Cliente: 'texto', Nombre: 'texto' }),
    ).toEqual([])
    // Con una columna numérica pero sin fechas, solo pregunta por el monto.
    expect(
      basicMappingQuestions({}, {}, [], { Total: 'numero', Nombre: 'texto' }),
    ).toEqual(['monto'])
  })

  it('no confunde un catalogo de costos con una tabla de ventas', () => {
    const mapping = {
      producto: 'SKU_Producto',
      costo: 'Costo Unitario',
      fecha: 'Fecha Vigencia',
    }
    expect(
      basicMappingQuestions(mapping, {}, [], {
        SKU_Producto: 'texto',
        'Costo Unitario': 'numero',
        'Fecha Vigencia': 'fecha',
      }),
    ).toEqual([])
    expect(requiresSalesAmountMapping(mapping)).toBe(false)
    expect(requiresSalesAmountMapping({ producto: 'SKU_Producto' })).toBe(true)
  })
})

describe('estado multihoja', () => {
  it('construye la vista de negocio con una sola hoja de ventas y una maestra de costos', () => {
    const scope: AnalysisScope = {
      mode: 'single',
      sheets: ['Ventas'],
      active_sheet: 'Ventas',
    }
    expect(shouldAutoBuildBusinessScope(
      scope,
      ['Ventas', 'Costos'],
      ['Ventas', 'Costos'],
      ['Ventas'],
      0,
    )).toBe(true)
    expect(shouldAutoBuildBusinessScope(
      scope,
      ['Ventas', 'Costos'],
      ['Ventas'],
      ['Ventas'],
      1,
    )).toBe(false)
  })

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

  it('persiste una seleccion reducida y descarta el alcance anterior', () => {
    expect(withSheetSelection({
      active_sheet: 'Control',
      available_sheets: ['Ventas', 'Costos', 'Control'],
      excluded_sheets: [],
      selected_sheets: ['Ventas', 'Costos', 'Control'],
      analysis_scope: {
        mode: 'append',
        sheets: ['Ventas', 'Control'],
        active_sheet: 'Control',
      },
      selection_mode: 'all',
    }, ['Ventas', 'Costos'], 'custom')).toEqual({
      active_sheet: 'Ventas',
      available_sheets: ['Ventas', 'Costos', 'Control'],
      excluded_sheets: ['Control'],
      selected_sheets: ['Ventas', 'Costos'],
      analysis_scope: {
        mode: 'single',
        sheets: ['Ventas'],
        active_sheet: 'Ventas',
      },
      selection_mode: 'custom',
    })
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
    expect(cleaningScopeState(
      ['Enero', 'Febrero', 'Marzo'],
      { ...sessions, Febrero: { ...sessions.Febrero, status: 'error' } },
    )).toBe('partial')
    expect(cleaningScopeState(['Enero'], sessions, true)).toBe('cleaning')
  })

  it('limpia en lote solo hojas preparadas pendientes y nunca borra duplicados por inferencia', () => {
    const sessions = {
      Enero: { standardization: { filas: 10 }, cleaning: { filas: 10 }, status: 'limpia' },
      Febrero: { standardization: { filas: 12 }, status: 'estandarizada' },
      Marzo: { standardization: { filas: 9 }, status: 'error' },
      Abril: { status: 'pendiente' },
    }
    expect(sheetsForAutomaticCleaning(
      ['Enero', 'Febrero', 'Marzo', 'Abril'],
      sessions,
    )).toEqual(['Febrero'])
    expect(sheetsForAutomaticCleaning(['Febrero'], sessions)).toEqual([])
  })

  it('reinicia la limpieza automática cuando cambia mapeo, reglas o estado', () => {
    const rules = {
      fechas: true,
      textos: true,
      duplicados: true,
      tipos: true,
      nulos: true,
      columnas_vacias: false,
      fuera_de_rango: true,
    }
    const base = {
      Enero: {
        standardization: { revision: 7 },
        cleaning: null,
        mappingOverride: { monto: 'Monto' },
        status: 'estandarizada',
      },
    }
    const original = automaticCleaningSignature('dataset-1', ['Enero'], base, rules)
    expect(automaticCleaningSignature(
      'dataset-1',
      ['Enero'],
      { Enero: { ...base.Enero, mappingOverride: { monto: 'Total' } } },
      rules,
    )).not.toBe(original)
    expect(automaticCleaningSignature(
      'dataset-1',
      ['Enero'],
      base,
      { ...rules, fechas: false },
    )).not.toBe(original)
    expect(automaticCleaningSignature(
      'dataset-1',
      ['Enero'],
      { Enero: { ...base.Enero, status: 'limpia' } },
      rules,
    )).not.toBe(original)
  })

  it('mantiene estable la firma si solo cambia el orden de las claves del mapeo', () => {
    const rules = {
      fechas: true,
      textos: true,
      duplicados: true,
      tipos: true,
      nulos: true,
      columnas_vacias: false,
      fuera_de_rango: true,
    }
    const left = automaticCleaningSignature('dataset-1', ['Enero'], {
      Enero: {
        standardization: { revision: 7 },
        mappingOverride: { monto: 'Monto', fecha: 'Fecha' },
        status: 'estandarizada',
      },
    }, rules)
    const right = automaticCleaningSignature('dataset-1', ['Enero'], {
      Enero: {
        standardization: { revision: 7 },
        mappingOverride: { fecha: 'Fecha', monto: 'Monto' },
        status: 'estandarizada',
      },
    }, rules)
    expect(right).toBe(left)
  })

  it('acumula success -> failure sin revivir un error ya resuelto', () => {
    const afterSuccess = updateBatchSheetErrors(
      { Enero: 'Fallo anterior', Auxiliar: 'No se pudo leer' },
      'Enero',
      null,
    )
    const afterFailure = updateBatchSheetErrors(
      afterSuccess,
      'Febrero',
      'No se pudo limpiar Febrero',
    )

    expect(afterFailure).toEqual({
      Auxiliar: 'No se pudo leer',
      Febrero: 'No se pudo limpiar Febrero',
    })
  })

  it('acumula failure -> success y limpia el error del reintento exitoso', () => {
    const afterFailure = updateBatchSheetErrors({}, 'Enero', 'Fallo temporal')
    const afterOtherSuccess = updateBatchSheetErrors(afterFailure, 'Febrero', null)
    const afterRetrySuccess = updateBatchSheetErrors(afterOtherSuccess, 'Enero', null)

    expect(afterOtherSuccess).toEqual({ Enero: 'Fallo temporal' })
    expect(afterRetrySuccess).toEqual({})
  })

  it('restaura un error por encima de un resultado anterior para permitir reintento', () => {
    expect(restoredSheetStatus('La limpieza fallo', true)).toBe('error')
    expect(restoredSheetStatus(null, true)).toBe('limpia')
    expect(restoredSheetStatus(undefined, false)).toBe('estandarizada')
  })

  it('separa el modo privado del alcance antes de llamar a una API', () => {
    const storedScope = {
      mode: 'single',
      sheets: ['Ventas'],
      active_sheet: 'Ventas',
      _selection_mode: 'custom',
    }

    const restored = restoredAnalysisSelection(storedScope)

    expect(restored).toEqual({
      analysisScope: { mode: 'single', sheets: ['Ventas'], active_sheet: 'Ventas' },
      selectionMode: 'custom',
    })
    expect(serializedAnalysisScope(storedScope)).toBe(
      JSON.stringify({ mode: 'single', sheets: ['Ventas'], active_sheet: 'Ventas' }),
    )
    expect(withPublicAnalysisScope({ analysis_scope: storedScope, ingresos: 100 })).toEqual({
      analysis_scope: { mode: 'single', sheets: ['Ventas'], active_sheet: 'Ventas' },
      ingresos: 100,
    })
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

  it('elige el grupo compatible mas grande aunque no sea el primero del libro', () => {
    const result = (columns: string[]) => ({
      preview: { columnas: columns },
      column_types: Object.fromEntries(columns.map((column) => [column, 'texto'])),
      mapeo: { monto: columns[columns.length - 1] },
      moneda: 'CLP',
    })
    expect(compatibleAppendSheets(
      ['Aux1', 'Aux2', 'Enero', 'Febrero', 'Marzo'],
      {
        Aux1: result(['ID', 'Nombre']),
        Aux2: result(['ID', 'Nombre']),
        Enero: result(['Fecha', 'Monto']),
        Febrero: result(['Fecha', 'Monto']),
        Marzo: result(['Fecha', 'Monto']),
      },
    )).toEqual(['Enero', 'Febrero', 'Marzo'])
  })

  it('incluye meses con una columna auxiliar opcional', () => {
    const result = (columns: string[]) => ({
      preview: { columnas: columns },
      column_types: Object.fromEntries(columns.map((column) => [column, column === 'Fecha' ? 'fecha' : column === 'Monto' ? 'numero' : 'texto'])),
      mapeo: { fecha: 'Fecha', monto: 'Monto' },
      moneda: 'CLP',
    })
    expect(compatibleAppendSheets(
      ['2024', '2025', '2026'],
      {
        '2024': result(['Fecha', 'Monto', 'Observacion']),
        '2025': result(['Fecha', 'Monto', 'Observacion', 'Observacion.1']),
        '2026': result(['Fecha', 'Monto', 'Observacion']),
      },
    )).toEqual(['2024', '2025', '2026'])
  })

  it('prefiere ventas y no confunde Stock + Precio_Lista + costo con transacciones', () => {
    const catalog = {
      preview: { columnas: ['ID_Producto', 'Producto', 'Stock', 'Costo_Unitario', 'Precio_Lista'] },
      column_types: {},
      mapeo: {
        producto: 'Producto',
        cantidad: 'Stock',
        costo: 'Costo_Unitario',
        monto: 'Precio_Lista',
      },
      moneda: 'CLP',
    }
    const sales = {
      preview: { columnas: ['ID_Venta', 'Fecha', 'Cantidad', 'Monto'] },
      column_types: {},
      mapeo: { fecha: 'Fecha', cantidad: 'Cantidad', monto: 'Monto' },
      moneda: 'CLP',
    }
    expect(compatibleAppendSheets(
      ['Catalogo A', 'Catalogo B', 'Ventas Enero', 'Ventas Febrero'],
      {
        'Catalogo A': catalog,
        'Catalogo B': catalog,
        'Ventas Enero': sales,
        'Ventas Febrero': sales,
      },
    )).toEqual(['Ventas Enero', 'Ventas Febrero'])
  })

  it('conserva una sola hoja de ventas para relacionarla con costos', () => {
    const sales = {
      preview: { columnas: ['Fecha', 'Cantidad', 'Monto'] },
      column_types: { Fecha: 'fecha', Cantidad: 'numero', Monto: 'numero' },
      mapeo: { fecha: 'Fecha', cantidad: 'Cantidad', monto: 'Monto' },
      moneda: 'CLP',
    }
    const catalog = {
      preview: { columnas: ['ID_Producto', 'Producto', 'Costo_Unitario', 'Precio_Lista'] },
      column_types: {},
      mapeo: { producto: 'Producto', costo: 'Costo_Unitario' },
      moneda: 'CLP',
    }
    expect(compatibleAppendSheets(
      ['Ventas', 'Productos'],
      { Ventas: sales, Productos: catalog },
    )).toEqual(['Ventas'])
  })

  it('sincroniza los checkboxes de append_join con el alcance real', () => {
    const scope: Extract<AnalysisScope, { mode: 'append_join' }> = {
      mode: 'append_join',
      sheets: ['Enero', 'Febrero', 'Productos'],
      append_sheets: ['Enero', 'Febrero'],
      active_sheet: 'Enero',
      join: {
        left_sheet: 'Enero',
        right_sheet: 'Productos',
        left_keys: ['ID_Producto'],
        right_keys: ['ID_Producto'],
        type: 'left',
      },
    }
    const updated = synchronizeAppendJoinSelection(
      scope,
      ['Enero', 'Febrero', 'Marzo'],
      ['Enero', 'Febrero', 'Marzo'],
    )
    expect(updated.blocked).toBeNull()
    expect(updated.appendSheets).toEqual(['Enero', 'Febrero', 'Marzo'])
    expect(updated.scope.append_sheets).toEqual(['Enero', 'Febrero', 'Marzo'])
    expect(updated.scope.sheets).toEqual(['Enero', 'Febrero', 'Marzo', 'Productos'])
  })

  it('permite cambiar la representante y conservar una sola hoja de ventas', () => {
    const scope: Extract<AnalysisScope, { mode: 'append_join' }> = {
      mode: 'append_join',
      sheets: ['Enero', 'Febrero', 'Productos'],
      append_sheets: ['Enero', 'Febrero'],
      active_sheet: 'Enero',
      join: {
        left_sheet: 'Enero',
        right_sheet: 'Productos',
        left_keys: ['ID_Producto'],
        right_keys: ['ID_Producto'],
        type: 'left',
      },
    }
    const withoutLeft = synchronizeAppendJoinSelection(
      scope,
      ['Febrero'],
      ['Enero', 'Febrero'],
    )
    expect(withoutLeft.blocked).toBeNull()
    expect(withoutLeft.appendSheets).toEqual(['Febrero'])
    expect(withoutLeft.scope.join.left_sheet).toBe('Febrero')
    expect(withoutLeft.scope.active_sheet).toBe('Febrero')

    const onlyLeft = synchronizeAppendJoinSelection(
      scope,
      ['Enero'],
      ['Enero', 'Febrero'],
    )
    expect(onlyLeft.blocked).toBeNull()
    expect(onlyLeft.appendSheets).toEqual(['Enero'])

    const empty = synchronizeAppendJoinSelection(scope, [], ['Enero', 'Febrero'])
    expect(empty.blocked).toBe('minimum_one_sheet')
    expect(empty.scope).toBe(scope)

    const unchanged = synchronizeAppendJoinSelection(
      scope,
      ['Enero', 'Febrero'],
      ['Enero', 'Febrero'],
    )
    expect(unchanged.scope).toBe(scope)
  })

  it('compara alcances por estructura y no por referencia de objeto', () => {
    const first: AnalysisScope = {
      mode: 'append',
      sheets: ['Enero', 'Febrero'],
      active_sheet: 'Enero',
    }
    const equivalent = JSON.parse(JSON.stringify(first)) as AnalysisScope
    expect(equivalent).not.toBe(first)
    expect(analysisScopesEqual(first, equivalent)).toBe(true)
    expect(analysisScopesEqual(first, { ...equivalent, active_sheet: 'Febrero' })).toBe(false)
  })

  it('explica una relacion insegura sin jerga de cardinalidad', () => {
    const candidate = {
      left_sheet: 'Ventas',
      right_sheet: 'Productos',
      left_keys: ['ID'],
      right_keys: ['ID'],
      type: 'left',
      coverage_left: 0.98,
      coverage_right: 1,
      overlap: 0,
      unique_left: 0.5,
      unique_right: 1,
      cardinality: 'muchos_a_uno',
      safe: false,
      reason: 'raw engine reason',
    } satisfies RelationshipCandidate
    expect(relationshipPlainMessage(candidate)).toContain('Ningún identificador')
    expect(relationshipPlainMessage(candidate)).not.toContain('muchos_a_uno')
  })

  it('autoelige solo una relación recomendada que enriquece costos', () => {
    const candidate = (
      right: string,
      purpose: RelationshipCandidate['purpose'],
      recommended: boolean,
      safe = true,
    ): RelationshipCandidate => ({
      left_sheet: 'Enero',
      right_sheet: right,
      left_keys: ['ID'],
      right_keys: ['ID'],
      type: 'left',
      coverage_left: 1,
      coverage_right: 1,
      overlap: 1,
      unique_left: 0.5,
      unique_right: 1,
      cardinality: 'muchos_a_uno',
      safe,
      reason: null,
      purpose,
      recommended,
      currency_compatible: true,
    })
    const selection = selectAppendJoinCostCandidates([
      candidate('Clientes', 'enriquecer_referencia', true),
      candidate('Productos', 'enriquecer_costos', true),
      candidate('Sucursales', 'enriquecer_referencia', false),
    ], ['Enero', 'Febrero'])
    expect(selection.automatic?.right_sheet).toBe('Productos')
    expect(selection.candidates.map((item) => item.right_sheet)).toEqual(['Productos'])

    const notRecommended = selectAppendJoinCostCandidates([
      candidate('Clientes', 'enriquecer_referencia', true),
      candidate('Productos', 'enriquecer_costos', false),
    ], ['Enero', 'Febrero'])
    expect(notRecommended.automatic).toBeNull()
    expect(notRecommended.candidates.map((item) => item.right_sheet)).toEqual(['Productos'])
  })

  it('conserva el motivo del candidato de costos bloqueado', () => {
    const blocked: RelationshipCandidate = {
      left_sheet: 'Enero',
      right_sheet: 'Productos_USD',
      left_keys: ['ID_Producto'],
      right_keys: ['ID_Producto'],
      type: 'left',
      coverage_left: 1,
      coverage_right: 1,
      overlap: 1,
      unique_left: 0.5,
      unique_right: 1,
      cardinality: 'muchos_a_uno',
      safe: false,
      reason: 'Ventas CLP y costos USD no son compatibles.',
      purpose: 'enriquecer_costos',
      recommended: false,
      currency_compatible: false,
    }
    const selection = selectAppendJoinCostCandidates([blocked], ['Enero', 'Febrero'])
    expect(selection.automatic).toBeNull()
    expect(selection.candidates).toEqual([])
    expect(selection.blocked && relationshipPlainMessage(selection.blocked)).toContain('CLP')
  })
})
