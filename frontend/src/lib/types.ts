export type ColumnType = 'fecha' | 'numero' | 'texto'

export interface StandardizeChanges {
  encabezados_normalizados: number
  textos_normalizados: number
  fechas_estandarizadas: number
  numeros_estandarizados: number
}

export interface StandardizeResult {
  archivo: string
  filas: number
  columnas: number
  column_types: Record<string, ColumnType>
  mapeo: Record<string, string | null>
  cambios: StandardizeChanges
  preview: {
    columnas: string[]
    antes: string[][]
    despues: string[][]
  }
}

export interface CleaningRules {
  fechas: boolean
  textos: boolean
  duplicados: boolean
  tipos: boolean
  nulos: boolean
  columnas_vacias: boolean
  fuera_de_rango: boolean
}

export const DEFAULT_RULES: CleaningRules = {
  fechas: true,
  textos: true,
  duplicados: true,
  tipos: true,
  nulos: true,
  columnas_vacias: true,
  fuera_de_rango: true,
}

export interface CleanProblems {
  duplicados: number
  valores_nulos: number
  fechas_invalidas: number
  textos_inconsistentes: number
  tipos_incorrectos: number
  columnas_vacias: number
  valores_fuera_de_rango: number
}

export interface CleanResult {
  archivo: string
  resumen: {
    filas_antes: number
    filas_despues: number
    columnas_antes: number
    columnas_despues: number
    calidad_antes: number
    calidad_despues: number
    aplicado: boolean
  }
  problemas: CleanProblems
  correcciones: Record<string, number>
  reglas_activas: CleaningRules
  preview: {
    columnas: string[]
    filas: string[][]
    issues: Array<{
      fila: number
      columna: string
      tipo: string
    }>
  }
  estandarizacion: StandardizeChanges
  column_types: Record<string, ColumnType>
  mapeo: Record<string, string | null>
}
