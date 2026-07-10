/** Tipos de las respuestas del motor de datos (api/app/routes/pipeline.py). */

export type ColumnType = 'fecha' | 'numero' | 'texto'

export interface StandardizeResult {
  archivo: string
  filas: number
  columnas: number
  column_types: Record<string, ColumnType>
  column_confidence?: Record<string, number>
  avisos?: string[]
  carga?: LoadInfo
  mapeo: Record<string, string>
  mapeo_extendido?: Record<string, DictionaryMatch>
  cambios: {
    encabezados_normalizados: number
    textos_normalizados: number
    fechas_estandarizadas: number
    numeros_estandarizados: number
  }
  preview: {
    columnas: string[]
    antes: string[][]
    despues: string[][]
  }
}

export interface CleanIssue {
  fila: number
  columna: string
  tipo: 'duplicado' | 'nulo' | 'fecha_invalida' | 'tipo_incorrecto'
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
  problemas: {
    duplicados: number
    valores_nulos: number
    fechas_invalidas: number
    textos_inconsistentes: number
    tipos_incorrectos: number
    columnas_vacias: number
    valores_fuera_de_rango: number
  }
  correcciones: {
    filas_duplicadas_a_eliminar: number
    valores_nulos_normalizados: number
    fechas_a_estandarizar: number
    textos_a_unificar: number
    tipos_a_corregir: number
    columnas_vacias_a_eliminar: number
    valores_fuera_de_rango_a_revisar: number
  }
  reglas_activas: CleaningRules
  preview: {
    columnas: string[]
    filas: string[][]
    issues: CleanIssue[]
  }
  estandarizacion: StandardizeResult['cambios']
  column_types: Record<string, ColumnType>
  mapeo: Record<string, string>
  reporte_calidad?: Record<string, ColumnQuality>
  avisos?: string[]
  duplicados_criterio?: string
  fusiones_texto?: { total: number; ejemplos: string[][] }
  carga?: LoadInfo
  dirigida?: DirectedInfo
}

/* ── Fase 7: reporte de calidad, carga y limpieza dirigida ── */

export interface LoadInfo {
  hoja_usada: string | null
  hojas_disponibles: string[]
  filas_titulo_omitidas: number
}

export interface DictionaryMatch {
  rol: string
  grupo: string
  tipo_dato: string
  rol_motor: string | null
  palabra_clave: string
  metodo: 'exacto' | 'contencion' | 'prefijo' | 'fuzzy' | 'ia'
  confianza: number
}

export interface ColumnQuality {
  rol: string | null
  rol_extendido?: string
  grupo_rol?: string
  match_diccionario?: { palabra_clave: string; metodo: string; confianza: number }
  tipo: ColumnType
  en_alcance: boolean
  vacia?: boolean
  nulos?: number
  nulos_pct?: number
  fechas_invalidas?: number
  tipos_incorrectos?: number
  outliers?: number
  confianza_tipo?: number | null
  convencion_numerica?: string
  politica_nulos?: string
}

export interface DirectedInfo {
  instrucciones: string
  columnas_incluir: string[]
  columnas_excluir: string[]
  reglas_forzadas: Partial<CleaningRules>
  avisos: string[]
  reconocido: boolean
  cupo: {
    disponible: boolean
    usadas_mes: number
    base: number
    addons: number
    restantes?: number
  }
}

export interface PlansUsage {
  disponible: boolean
  plan: string
  enforcement: boolean
  insights: { usadas: number; limite: number }
  limpieza: { usadas_mes: number; base: number; addons: number }
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

/* ── Fase 2: respuesta de POST /metrics ── */

export interface KpiValue {
  valor: number
  variacion_pct: number | null
}

export interface GroupRow {
  nombre: string
  ingresos: number
  porcentaje: number
  utilidad?: number
  margen_pct?: number | null
}

/** Fase 8: qué dimensiones reales trae el dataset (adapta Explorar/Resumen). */
export interface DatasetDimensions {
  fecha: boolean
  monto: boolean
  costo: boolean
  cantidad: boolean
  categoria: boolean
  producto: boolean
  canal: boolean
  sucursal: boolean
  cliente: boolean
  vendedor: boolean
}

export interface MetricsResult {
  archivo: string
  calidad_datos: number
  moneda: string
  mapeo: Record<string, string>
  dimensiones?: DatasetDimensions
  agrupado_por_canal: 'canal' | 'sucursal' | null
  periodo: { desde: string | null; hasta: string | null; meses_disponibles: string[] }
  kpis: {
    ingresos_totales: KpiValue
    transacciones: number
    ticket_promedio: number
    unidades_totales?: number
    gastos_totales: KpiValue | null
    ganancia_neta: KpiValue | null
    margen_utilidad_pct: { valor: number | null; variacion_puntos: number | null } | null
    flujo_caja: KpiValue | null
  }
  evolucion_mensual: Array<{ mes: string; ingresos: number; gastos?: number; utilidad?: number }>
  por_categoria?: GroupRow[]
  ventas_por_canal?: GroupRow[]
  top_productos?: GroupRow[]
  proyeccion: {
    crecimiento_pct: number
    crecimiento_trimestre_pct: number | null
    meses: Array<{ mes: string; ingresos: number }>
  } | null
  indicadores_financieros: {
    disponible: boolean
    nota: string
    items: Record<string, number | null>
  }
  advertencias: string[]
}
