/** Tipos de las respuestas del motor de datos (api/app/routes/pipeline.py). */

export type ColumnType = 'fecha' | 'numero' | 'texto'

export interface StandardizeResult {
  revision?: number
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
  revision?: number
  persistencia?: {
    guardada: boolean
    mensaje?: string
  }
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
  moneda?: string
  moneda_mixta?: boolean
  moneda_detalle?: {
    dominante: string
    detectadas: string[]
    conteos: Record<string, number>
    mixta: boolean
    advertencia: string | null
    conteos_por_columna: Record<string, Record<string, number>>
  }
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
  clasificacion_hojas?: SheetClassification[]
  filas_titulo_omitidas: number
  formulas?: FormulaReport | null
}

export interface SheetClassification {
  nombre: string
  clasificacion: 'datos' | 'auxiliar' | 'ambigua'
  recomendacion: 'procesar' | 'conservar_sin_procesar'
  motivos: string[]
  estructura: {
    filas_muestra: number
    filas_datos_muestra: number
    columnas_muestra: number
    celdas_no_vacias_muestra: number
    densidad_muestra: number
    fila_encabezado: number | null
    formulas_muestra?: number
    celdas_combinadas?: number
    filas_estimadas?: number
    columnas_estimadas?: number
  }
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
  status?: SheetProcessingStatus
  error?: string
  revision?: number
}

export interface SheetManifest {
  hojas: SheetManifestEntry[]
}

export type SheetProcessingStatus =
  | 'pendiente'
  | 'estandarizando'
  | 'estandarizada'
  | 'limpiando'
  | 'limpia'
  | 'error'
  | 'no_seleccionada'

export interface AnalysisJoin {
  left_sheet: string
  right_sheet: string
  left_keys: string[]
  right_keys: string[]
  type: 'left'
}

export type AnalysisScope =
  | { mode: 'single'; sheets: string[]; active_sheet: string }
  | { mode: 'append'; sheets: string[]; active_sheet: string }
  | { mode: 'join'; sheets: string[]; active_sheet: string; join: AnalysisJoin }
  | {
      mode: 'append_join'
      sheets: string[]
      append_sheets: string[]
      active_sheet: string
      join: AnalysisJoin
    }

export interface RelationshipCandidate extends AnalysisJoin {
  coverage_left: number
  coverage_right: number
  overlap: number
  unique_left: number
  unique_right: number
  cardinality: 'uno_a_uno' | 'muchos_a_uno' | 'uno_a_muchos' | 'muchos_a_muchos' | 'sin_relacion_segura'
  safe: boolean
  reason: string | null
  purpose?: 'enriquecer_costos' | 'enriquecer_referencia' | 'otra_relacion'
  recommended?: boolean
  currency_compatible?: boolean
}

export interface RelationshipResult {
  candidates: RelationshipCandidate[]
  safe_count: number
  manual?: RelationshipCandidate | null
  message: string | null
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
  /** Neto del grupo / neto total. Coincide con los montos y sectores del
   * gráfico; puede ser negativo si un grupo solo contiene devoluciones. */
  participacion_neta_pct?: number | null
  ventas_brutas?: number
  devoluciones?: number
  ventas_netas?: number
  costo?: number
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
    sin_fecha?: { filas: number; monto: number | null; excluidas_por_filtro: boolean }
  }
  kpis: {
    ingresos_totales: KpiValue | null
    transacciones: number
    ticket_promedio: number | null
    unidades_totales?: number
    gastos_totales: KpiValue | null
    ganancia_neta: KpiValue | null
    margen_utilidad_pct: { valor: number | null; variacion_puntos: number | null } | null
    flujo_caja: KpiValue | null
    /** Fase 10: % de filas con ingreso que también traen costo (margen confiable). */
    cobertura_costos?: { filas_con_ingreso: number; filas_con_ingreso_y_costo: number; pct: number }
    /** Bases distintas: costo total conocido puede incluir filas sin monto;
     * utilidad y margen usan exclusivamente filas pareadas. */
    base_costos?: {
      filas_con_costo: number
      costo_total_conocido: number
      filas_pareadas: number
      costo_pareado: number
      ingresos_pareados: number
    } | null
    /** Fase 12b §12: filas con monto legible — base real del ticket promedio. */
    registros_con_monto?: number
    /** Fase 12b §16: montos negativos (devoluciones/reversas) — los ingresos son netos. */
    devoluciones?: { monto: number; filas: number } | null
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
  datos_monetarios_disponibles?: boolean
  bloqueo_monetario?: { codigo: string; mensaje: string | null }
  duplicados?: { detectados: number; eliminados: number; conservados: number }
  calculo_costos?: {
    origen: 'cantidad_por_costo_unitario' | 'columna_costo'
    columna_costo: string | null
    columna_cantidad: string | null
  } | null
  calidad_costos?: {
    registros_atipicos: number
    no_positivos: number
    limite_superior_iqr: number
    costo_absoluto_atipico: number
    participacion_costo_absoluto_pct: number
  } | null
  analysis_scope?: AnalysisScope
  analysis_provenance?: Record<string, unknown>
  tipo_analisis?: 'catalogo_productos' | 'campanas_marketing' | 'inventario' | 'generico'
  analisis_productos?: {
    productos: number
    referencia_tipo?: 'precio_lista' | 'costo_total_unitario' | null
    costos: { promedio: number | null; mediana: number | null; minimo: number | null; maximo: number | null }
    precios_lista: { promedio: number | null; mediana: number | null; minimo: number | null; maximo: number | null }
    margen_potencial: { promedio: number | null; mediana: number | null; minimo: number | null; maximo: number | null }
    totales_catalogo_unitario?: {
      costo: number
      precio_lista: number
      utilidad_potencial: number
      productos_con_comparacion: number
    } | null
    cobertura_costo_pct: number
    costos_tipicos?: { promedio: number | null; mediana: number | null; minimo: number | null; maximo: number | null }
    costos_a_revisar?: {
      registros: number
      no_positivos: number
      sobre_limite_iqr: number
      limite_superior_iqr: number | null
    }
    ranking_costos: Array<{ producto: string; costo: number; precio_lista: number | null; margen_potencial_pct: number | null; requiere_revision?: boolean }>
    categorias: Array<{ nombre: string; productos: number }>
    marcas: Array<{ nombre: string; productos: number }>
    activos: number | null
    inactivos: number | null
  }
  analisis_campanas?: {
    campanas: number
    inversion: number | null
    impresiones: number
    clics: number
    ctr_pct: number | null
    cpc: number | null
    plataformas: Array<{ nombre: string; registros: number }>
    estados: Array<{ nombre: string; registros: number }>
    /** Fase 18: métricas por plataforma para graficar. */
    por_plataforma?: Array<{
      nombre: string
      campanas: number
      inversion: number
      impresiones: number
      clics: number
      ctr_pct: number | null
      cpc: number | null
    }>
    clics_sobre_impresiones?: number
  }
  analisis_inventario?: {
    registros: number
    productos: number
    stock_total: number
    stock_minimo_total: number
    valor_inventario?: number | null
    costo_referencia_promedio?: number | null
    unidades_comprometidas?: number | null
    diferencia_conteo?: number | null
    bajo_minimo: number
    stocks_negativos?: number
    cobertura_stock_pct: number
    sucursales: Array<{ nombre: string; registros: number }>
    /** Fase 18: existencia y quiebres por sucursal para graficar. */
    por_sucursal?: Array<{
      nombre: string
      registros: number
      stock: number
      bajo_minimo: number
      stocks_negativos: number
    }>
    columna_actualizacion: string | null
  }
  analisis_generico?: {
    registros: number
    columnas: number
    celdas_informadas_pct: number
    columnas_disponibles: string[]
    /** Fase 18: perfil con contenido para hojas de clientes, sucursales,
     * trabajadores, metas u otras no transaccionales. */
    subtipo?:
      | 'clientes'
      | 'sucursales'
      | 'trabajadores'
      | 'metas'
      | 'productos'
      | 'proveedores'
      | 'compras'
      | 'gastos'
      | 'cobranzas'
      | 'historial_costos'
      | null
    distribuciones?: Array<{
      columna: string
      valores: Array<{ nombre: string; registros: number }>
      valores_totales: number
    }>
    numericas?: Array<{
      columna: string
      total: number | null
      promedio: number
      mediana: number
      minimo: number
      maximo: number
      formato?: 'moneda' | 'porcentaje' | 'numero'
      destacado?: 'total' | 'promedio'
      valores_validos?: number
      fuera_rango?: number
    }>
    evolucion?: {
      columna: string
      operacion: 'total' | 'promedio'
      formato: 'moneda' | 'porcentaje' | 'numero'
      valores: Array<{ mes: string; valor: number }>
    } | null
  }
  /** Fase 18: agrupaciones de ventas por columnas categóricas adicionales
   * (sucursal, región, zona…), incluidas las enriquecidas por una relación. */
  agrupaciones_flexibles?: Array<{
    columna: string
    grupos: GroupRow[]
    grupos_totales: number
    fuera_de_rango?: { filas: number; monto_asociado: number }
  }>
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
  selected_sheets?: string[]
  sheet_errors?: Record<string, string>
  analysis_scope?: AnalysisScope | null
  selection_mode?: 'all' | 'custom'
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
