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
  mojibake_auditoria?: MojibakeAudit[]
  cambios: {
    encabezados_normalizados: number
    textos_normalizados: number
    fechas_estandarizadas: number
    numeros_estandarizados: number
    celdas_con_espacios_normalizados?: number
    celdas_con_variantes_unificadas?: number
    celdas_textuales_unicas_modificadas?: number
    placeholders_detectados?: number
    mojibake_detectado?: number
    mojibake_reparado?: number
  }
  preview: {
    columnas: string[]
    antes: string[][]
    despues: string[][]
  }
}

export interface CleanIssue {
  fila: number
  fila_origen?: number
  columna: string
  tipo: 'duplicado' | 'nulo' | 'nulo_semantico' | 'fecha_invalida' | 'tipo_incorrecto'
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
    /** Fase 10: duplicados con misma clave pero montos distintos (revisión manual). */
    duplicados_probables?: number
    valores_nulos: number
    nulos_fisicos?: number
    nulos_semanticos?: number
    posibles_nulos_estructurales?: number
    fechas_invalidas: number
    textos_inconsistentes: number
    tipos_incorrectos: number
    columnas_vacias: number
    montos_cero?: number
    montos_negativos?: number
    outliers_iqr?: number
    valores_fuera_de_rango: number
  }
  correcciones: {
    filas_duplicadas_a_eliminar: number
    filas_duplicadas_eliminadas?: number
    valores_nulos_normalizados: number
    fechas_a_estandarizar: number
    textos_a_unificar: number
    tipos_a_corregir: number
    columnas_vacias_a_eliminar: number
    valores_fuera_de_rango_a_revisar: number
  }
  reglas_activas: CleaningRules
  opciones_aplicacion?: CleaningOptions
  duplicados_detalle?: DuplicateDetails
  nulos_detalle?: NullDetails
  inconsistencias_identidad?: IdentityInconsistencies
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
  mojibake_auditoria?: MojibakeAudit[]
  carga?: LoadInfo
  dirigida?: DirectedInfo
}

export interface DuplicateDetails {
  exactos: number
  normalizados: number
  conflictos_id: number
  grupos: number
  filas_involucradas: number
  tamano_maximo_grupo: number
  grupos_contiguos: number
  eliminacion_habilitada: boolean
  filas_seleccionadas_para_eliminar: number
  filas_eliminadas: number
  posible_granularidad_omitida?: boolean
  auditoria_truncada?: boolean
}

export interface StructuralNullPattern {
  columna: string
  agrupado_por: string
  grupo: string
  filas_grupo: number
  vacio_en_grupo_pct: number
  informado_fuera_pct: number
  filas_origen_ejemplo: number[]
  mensaje: string
}

export interface NullDetails {
  fisicos: number
  semanticos: number
  posibles_estructurales: StructuralNullPattern[]
}

export interface MojibakeAudit {
  columna?: string
  valor_original: string
  valor_propuesto: string | null
  metodo: string | null
  confianza: number
  aplicado: boolean
  motivo: string
  ocurrencias: number
}

export interface IdentityInconsistencies {
  nombre_con_varios_ids: {
    conteo: number
    ejemplos: Array<{
      entidad: string
      columna_nombre: string
      columna_id: string
      nombre: string
      cantidad_ids: number
      ids_ejemplo: string[]
      filas_origen: number[]
    }>
  }
  id_con_varios_nombres: {
    conteo: number
    ejemplos: Array<{
      entidad: string
      columna_nombre: string
      columna_id: string
      id: string
      cantidad_nombres: number
      nombres_ejemplo: string[]
      filas_origen: number[]
    }>
  }
  pares_analizados: Array<{
    entidad: string
    columna_nombre: string
    columna_id: string
  }>
}

/* ── Fase 7: reporte de calidad, carga y limpieza dirigida ── */

export interface LoadInfo {
  hoja_usada: string | null
  hojas_disponibles: string[]
  filas_titulo_omitidas: number
  formulas?: FormulaReport | null
}

export interface FormulaReport {
  disponible: boolean
  total: number
  volatiles: number
  identificadores_volatiles: string[]
  error?: string
  por_columna: Record<
    string,
    {
      total: number
      volatiles: number
      valores_fijos: number
      columna_identificadora: boolean
      ejemplos: Array<{
        fila_origen: number
        formula: string
        volatil: boolean
      }>
    }
  >
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
  nulos_fisicos?: number
  nulos_semanticos?: number
  posibles_nulos_estructurales?: number
  nulos_pct?: number
  fechas_invalidas?: number
  tipos_incorrectos?: number
  outliers?: number
  montos_cero?: number
  montos_negativos?: number
  outliers_iqr?: {
    q1: number
    q3: number
    iqr: number
    limite_inferior: number
    limite_superior: number
    bajo_limite: number
    sobre_limite: number
    total: number
  }
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
  insights: { usadas: number; limite: number; ilimitado?: boolean }
  limpieza: { usadas_mes: number; base: number; addons: number; ilimitado?: boolean }
}

export interface CleaningRules {
  fechas: boolean
  textos: boolean
  /** @deprecated Detectar es obligatorio; eliminar usa CleaningOptions. */
  duplicados: boolean
  tipos: boolean
  nulos: boolean
  columnas_vacias: boolean
  fuera_de_rango: boolean
}

export interface CleaningOptions {
  eliminar_duplicados: boolean
}

export interface SheetManifestEntry {
  nombre: string
  procesar: boolean
  rules: Partial<CleaningRules>
  mapping: Record<string, string>
  scope: { incluir?: string[]; excluir?: string[] }
  eliminar_duplicados: boolean
}

export interface SheetManifest {
  hojas: SheetManifestEntry[]
}

export const DEFAULT_CLEANING_OPTIONS: CleaningOptions = {
  eliminar_duplicados: false,
}

export const DEFAULT_RULES: CleaningRules = {
  fechas: true,
  textos: true,
  duplicados: true,
  tipos: true,
  nulos: true,
  // Fase 12b §9: detectar sí, eliminar NO por defecto (filosofía conservadora)
  columnas_vacias: false,
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
  /** Neto del grupo / ventas brutas totales — muestra el efecto de las
   * devoluciones, pero NO es una distribución (no suma 100%). */
  porcentaje: number
  /** Fase 14b: distribución REAL — brutas del grupo / brutas totales.
   * Suma ≈100% y es la base de toda afirmación de CONCENTRACIÓN. */
  participacion_bruta_pct?: number | null
  ventas_brutas?: number
  devoluciones?: number
  ventas_netas?: number
  utilidad?: number
  margen_pct?: number | null
  /** Fase 12b: base de cálculo del grupo — sin esto una categoría con 1 fila
   * con costo "competía" en rentabilidad contra otra con mil. */
  filas?: number
  filas_pareadas?: number
  cobertura_costos_pct?: number
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
  /** Fase 15: montos en MÁS de una moneda — los totales mezclan monedas y la
   * UI bloquea los KPIs monetarios (jamás mostrar una cifra sumada inválida). */
  moneda_mixta?: boolean
  mapeo: Record<string, string>
  dimensiones?: DatasetDimensions
  agrupado_por_canal: 'canal' | 'sucursal' | null
  periodo: {
    desde: string | null
    hasta: string | null
    meses_disponibles: string[]
    /** Fase 13 (P0.4): el mes seleccionado esta incompleto — la variacion compara dias equivalentes. */
    mes_parcial?: boolean
  }
  kpis: {
    ingresos_totales: KpiValue
    transacciones: number
    ticket_promedio: number
    unidades_totales?: number
    gastos_totales: KpiValue | null
    ganancia_neta: KpiValue | null
    margen_utilidad_pct: { valor: number | null; variacion_puntos: number | null } | null
    flujo_caja: KpiValue | null
    /** Fase 10: % de filas con ingreso que también traen costo (margen confiable). */
    cobertura_costos?: { filas_con_ingreso: number; filas_con_ingreso_y_costo: number; pct: number }
    /** Fase 12b §12: filas con monto legible — base real del ticket promedio. */
    registros_con_monto?: number
    /** Fase 12b §16: montos negativos (devoluciones/reversas) — los ingresos son netos. */
    devoluciones?: { monto: number; filas: number }
  }
  evolucion_mensual: Array<{
    mes: string
    ingresos: number
    /** Fase 14: el ÚLTIMO mes con datos hasta antes de fin de mes se marca
     * parcial — proyección lo excluye y Alertas no lo compara con completos. */
    parcial?: boolean
    cobertura_hasta_dia?: number
    dias_del_mes?: number
    gastos?: number
    utilidad?: number
    /** Fase 12b §13: margen del mes con el MISMO denominador pareado que el KPI global. */
    margen_pareado_pct?: number | null
    cobertura_costos_pct?: number | null
  }>
  por_categoria?: GroupRow[]
  ventas_por_canal?: GroupRow[]
  top_productos?: GroupRow[]
  /** Fase 15: líderes calculados sobre TODOS los productos ANTES del recorte
   * a 12 — la concentración comercial usa por_ventas_brutas. */
  lideres_productos?: {
    por_ventas_brutas?: { nombre: string; ventas_brutas: number; participacion_bruta_pct?: number | null } | null
    por_ventas_netas?: { nombre: string; ventas_netas: number } | null
    por_utilidad?: { nombre: string; utilidad: number } | null
    mayor_devolucion?: { nombre: string; devoluciones: number } | null
    total_productos?: number
  } | null
  /** Fase 12: concentración de clientes (riesgo de dependencia) — solo si hay columna cliente. */
  clientes?: {
    unicos: number
    top: GroupRow[]
    concentracion_top_pct: number | null
    /** Fase 12b §21: % de los ingresos que tienen cliente identificado. */
    cobertura_identificacion_pct?: number | null
  }
  /** Fase 12: en qué días de la semana se concentra la venta — solo si hay fechas. */
  por_dia_semana?: Array<{ dia: string; ingresos: number; transacciones: number }>
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

/** Compact response from POST /restore/latest. */
export interface RestoreLatestResult {
  dataset: {
    id: string
    name: string
    source: string
    storage_path: string
    status: 'cargado' | 'estandarizado' | 'limpio' | 'error'
  } | null
  standardization?: StandardizeResult
  cleaning?: CleanResult | null
  metrics?: MetricsResult | null
  mapping?: Record<string, string> | null
  eliminar_duplicados?: boolean
  active_sheet?: string | null
  available_sheets?: string[]
  excluded_sheets?: string[]
  combine_sheets?: boolean
  sheet_sessions?: Record<string, {
    standardization: StandardizeResult
    cleaning: CleanResult | null
    metrics: MetricsResult | null
    mapping: Record<string, string> | null
    eliminar_duplicados: boolean
  }>
  source: 'snapshot' | 'computed' | 'empty'
}
