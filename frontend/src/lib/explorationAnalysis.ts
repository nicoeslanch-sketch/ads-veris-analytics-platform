import type { GroupRow, MetricsResult } from './types'

export type ExplorationFormat = 'moneda' | 'porcentaje' | 'numero'
export interface ExplorationPoint { period: string; value: number | null; partial?: boolean }
export interface ExplorationGroup { name: string; value: number | null; records?: number; coverage?: number }
export interface ExplorationMeasure {
  id: string
  label: string
  value: number | null
  format: ExplorationFormat
  formula: string
  series: ExplorationPoint[]
  dimensions: Array<{ name: string; groups: ExplorationGroup[]; totalGroups?: number }>
  movement?: { dimension: string; values: Array<{ period: string; name: string; value: number }> }
}
export interface ExplorationModel {
  subject: string
  context: string
  measures: ExplorationMeasure[]
  cautions: string[]
  checks: string[]
  relations: Array<{ name: string; rows: number; matched: number; unmatched: number; missing: number | null; coverage: number }>
}

export function explorationValue(value: number | null | undefined, format: ExplorationFormat, currency: string): string {
  if (value == null || !Number.isFinite(value)) return 'No disponible'
  const rendered = new Intl.NumberFormat('es-CL', { maximumFractionDigits: format === 'moneda' && currency === 'CLP' ? 0 : 2 }).format(value)
  return format === 'moneda' ? `${rendered} ${currency}` : format === 'porcentaje' ? `${rendered}%` : rendered
}

const label = (value: string) => value.replace(/_/g, ' ')
const valid = (value: number | null | undefined): value is number => value != null && Number.isFinite(value)
const blankMeasure = (id: string, title: string, value: number | null | undefined, format: ExplorationFormat, formula: string): ExplorationMeasure => ({
  id, label: title, value: value ?? null, format, formula, series: [], dimensions: [],
})

export function buildExplorationModel(m: MetricsResult): ExplorationModel {
  const model: ExplorationModel = { subject: 'Actividad registrada', context: '', measures: [], cautions: [], checks: [], relations: [] }
  const money = (value: number | null | undefined) => explorationValue(value, 'moneda', m.moneda)
  const count = (value: number) => explorationValue(value, 'numero', m.moneda)
  const business = m.analisis_negocio
  const collection = business?.cobranza
  const inventory = m.analisis_inventario
  const generic = m.analisis_generico
  const catalog = m.analisis_productos
  const campaigns = m.analisis_campanas

  if (collection) {
    model.subject = 'Cobranza y recaudación'
    model.context = `${count(collection.kpis.registros)} registros; ${count(collection.kpis.registros_cobranza)} asociados a cobranza. La recaudación total y la cobranza no son bases intercambiables.`
    for (const [id, title, value] of [
      ['recaudacion_cobranza', 'Recaudación de cobranza', collection.kpis.recaudacion_cobranza],
      ['recaudacion_total', 'Recaudación total', collection.kpis.recaudacion_total],
    ] as const) {
      const measure = blankMeasure(id, title, value, 'moneda', id === 'recaudacion_total' ? 'Suma de la recaudación total del período.' : 'Suma del monto identificado como cobranza del período.')
      // The collection series can be daily or weekly; no monthly completeness is asserted.
      measure.series = collection.evolucion.map((row) => ({ period: row.periodo, value: row[id], partial: true }))
      measure.dimensions = [{ name: 'Equipo', groups: collection.equipos.map((row) => ({ name: [row.equipo, row.subgrupo].filter(Boolean).join(' / '), value: row[id] })) }]
      if (id === 'recaudacion_cobranza') measure.dimensions.push(
        ...[['Agencia de pago', collection.agencias], ['Forma de pago', collection.formas_pago], ['Descripción del pago', collection.descripciones_pago]].map(([name, rows]) => ({ name: name as string, groups: (rows as typeof collection.agencias).map((row) => ({ name: row.nombre, value: row.valor })) })),
        { name: 'Período cotizado', groups: collection.periodos_cotizados.map((row) => ({ name: row.periodo, value: row.valor })) },
      )
      measure.dimensions = measure.dimensions.filter((item) => item.groups.length)
      model.measures.push(measure)
    }
    model.cautions.push('Los pagos observados no bastan para calcular morosidad ni liquidez: faltan deuda exigible, vencimientos y saldos a la misma fecha.', ...collection.notas)
    model.checks.push('Contrasta los equipos con la misma cartera asignada y el mismo período antes de atribuir diferencias a su gestión.')
  } else if (business?.servicios) {
    const services = business.servicios
    model.subject = 'Servicios y órdenes de trabajo'
    model.context = `${count(services.kpis.ot_total)} órdenes de trabajo; ${count(services.kpis.ot_abiertas)} abiertas. Las órdenes y las líneas de servicio son bases distintas.`
    for (const [id, title, value] of [
      ['ingresos', 'Ingresos por servicios', services.kpis.ventas_netas],
      ['utilidad_bruta', 'Utilidad bruta de servicios', services.kpis.utilidad_bruta],
      ['utilidad_operacional', 'Resultado operacional', services.kpis.utilidad_operacional],
    ] as const) {
      const measure = blankMeasure(id, title, value, 'moneda', id === 'ingresos' ? 'Ingresos de materiales, horas y contratos incluidos.' : id === 'utilidad_bruta' ? 'Ingresos menos costos directos asociados.' : 'Utilidad bruta menos gastos de estructura asignados.')
      measure.series = services.evolucion.map((row) => ({ period: row.mes, value: row[id], partial: row.parcial }))
      if (id !== 'utilidad_operacional') measure.dimensions = [['Tipo de orden', services.por_tipo_ot], ['Segmento', services.por_segmento], ['Cliente', services.por_cliente]].map(([name, rows]) => ({ name: name as string, groups: (rows as typeof services.por_tipo_ot).map((row) => ({ name: row.nombre, value: id === 'ingresos' ? row.ingresos : row.utilidad, records: row.registros })) }))
      model.measures.push(measure)
    }
    model.cautions.push(...services.trazabilidad.advertencias, 'El resultado operacional no demuestra liquidez: los ingresos devengados y los cobros pueden ocurrir en fechas distintas.')
    model.checks.push('Contrasta las órdenes con pérdida por materiales, horas y costos directos; comprueba horas no facturables antes de atribuir la diferencia al precio.')
  } else if (inventory) {
    model.subject = 'Existencias y reposición'
    model.context = `${count(inventory.registros)} registros de inventario y ${count(inventory.productos)} productos distintos${inventory.fecha_corte ? ` al ${inventory.fecha_corte}` : ''}.`
    const stock = blankMeasure('stock', 'Unidades en stock', inventory.stock_total, 'numero', 'Suma de existencias de los registros incluidos, no suma de ventas.')
    stock.dimensions = [{ name: 'Sucursal', groups: (inventory.por_sucursal ?? []).map((row) => ({ name: row.nombre, value: row.stock, records: row.registros })) }]
    const shortage = blankMeasure('bajo_minimo', 'Registros bajo mínimo', inventory.bajo_minimo, 'numero', 'Cantidad de registros cuyo stock es menor a su mínimo; un producto puede aparecer en varias sucursales.')
    shortage.dimensions = [{ name: 'Sucursal', groups: (inventory.por_sucursal ?? []).map((row) => ({ name: row.nombre, value: row.bajo_minimo, records: row.registros })) }]
    model.measures.push(stock, shortage)
    if (valid(inventory.valor_inventario)) model.measures.push(blankMeasure('valor', 'Valor de inventario', inventory.valor_inventario, 'moneda', 'Valoración calculada con existencias y costos de referencia disponibles.'))
    model.cautions.push(`Cobertura de stock legible: ${count(inventory.cobertura_stock_pct)}%. Bajo mínimo cuenta registros, no productos únicos.`, 'Un corte de inventario no demuestra una tendencia ni permite calcular rotación sin consumo o costo de ventas comparable.')
    if ((inventory.stocks_negativos ?? 0) > 0) model.cautions.push(`${count(inventory.stocks_negativos!)} registros tienen stock negativo; comprueba ajustes, reservas y la fecha del conteo.`)
    model.checks.push('Revisa producto y sucursal en los registros bajo mínimo; contrasta unidades comprometidas y plazos de reposición antes de comprar.')
  } else if (generic) {
    model.subject = generic.subtipo ? label(generic.subtipo) : 'Datos de la hoja'
    model.context = `${count(generic.registros)} registros y ${count(generic.columnas)} columnas; ${count(generic.celdas_informadas_pct)}% de celdas informadas.`
    for (const numeric of generic.numericas ?? []) {
      const isAverage = numeric.destacado === 'promedio' || numeric.total == null
      const measure = blankMeasure(numeric.columna, numeric.etiqueta ?? label(numeric.columna), isAverage ? numeric.promedio : numeric.total, numeric.formato ?? 'numero', `${isAverage ? 'Promedio' : 'Suma'} de ${numeric.columna}, usando ${numeric.valores_validos == null ? 'los valores numéricos legibles' : `${count(numeric.valores_validos)} valores legibles`}. Mediana: ${explorationValue(numeric.mediana, numeric.formato ?? 'numero', m.moneda)}.`)
      measure.dimensions = (generic.desgloses ?? []).filter((row) => row.columna === numeric.columna).map((row) => ({ name: label(row.dimension), groups: row.valores.map((group) => ({ name: group.nombre, value: group.valor, records: group.registros })), totalGroups: row.valores_totales }))
      if (generic.evolucion?.columna === numeric.columna) measure.series = generic.evolucion.valores.map((row) => ({ period: row.mes, value: row.valor, partial: true }))
      model.measures.push(measure)
    }
    if (!model.measures.length) {
      const records = blankMeasure('registros', 'Registros', generic.registros, 'numero', 'Cantidad de filas; no equivale necesariamente a personas, documentos ni IDs únicos.')
      records.dimensions = (generic.distribuciones ?? []).map((row) => ({ name: label(row.columna), groups: row.valores.map((group) => ({ name: group.nombre, value: group.registros })), totalGroups: row.valores_totales }))
      model.measures.push(records)
    }
    model.cautions.push('Los totales describen esta hoja; no se suman automáticamente a ventas, costos o caja de otras hojas. La completitud no garantiza que los valores sean correctos.')
    if (generic.subtipo === 'gastos') model.cautions.push('Gasto, neto e IVA son medidas distintas. Sin ingresos y costos comparables no se puede concluir utilidad o rentabilidad.')
    if (generic.evolucion) model.cautions.push('La serie no certifica meses completos: no se presenta una variación mensual como crecimiento comparable.')
    model.checks.push('Comprueba la unidad, el período y el significado de la columna elegida; un porcentaje se analiza como promedio, no como suma de porcentajes.')
  } else if (catalog) {
    model.subject = 'Catálogo y costos de referencia'
    model.context = `${count(catalog.productos)} productos; ${count(catalog.cobertura_costo_pct)}% con costo disponible.`
    const cost = blankMeasure('costo', 'Costo de referencia promedio', catalog.costos.promedio, 'moneda', 'Promedio de costos unitarios disponibles; no representa el costo total de ventas.')
    cost.dimensions = [{ name: 'Producto', groups: catalog.ranking_costos.map((row) => ({ name: row.producto, value: row.costo })) }]
    model.measures.push(cost, blankMeasure('precio', 'Precio de lista promedio', catalog.precios_lista.promedio, 'moneda', 'Promedio de precios de catálogo, no ventas realizadas.'))
    model.cautions.push('El margen potencial del catálogo no es utilidad realizada: faltan cantidades vendidas, descuentos, devoluciones y costos asociados a cada venta.')
    model.checks.push('Relaciona productos con ventas mediante un ID único de referencia y revisa costos atípicos antes de comparar márgenes.')
  } else if (campaigns) {
    model.subject = 'Campañas y respuesta observada'
    model.context = `${count(campaigns.campanas)} campañas, ${count(campaigns.impresiones)} impresiones y ${count(campaigns.clics)} clics.`
    for (const [id, title, value, format, formula] of [
      ['inversion', 'Inversión', campaigns.inversion, 'moneda', 'Suma de inversión registrada.'],
      ['clics', 'Clics', campaigns.clics, 'numero', 'Suma de clics registrados.'],
      ['ctr_pct', 'CTR', campaigns.ctr_pct, 'porcentaje', 'Clics / impresiones × 100; no promedio simple de CTR de campañas.'],
    ] as const) {
      const measure = blankMeasure(id, title, value, format, formula)
      measure.dimensions = [{ name: 'Plataforma', groups: (campaigns.por_plataforma ?? []).map((row) => ({ name: row.nombre, value: row[id], records: row.campanas })) }]
      model.measures.push(measure)
    }
    model.cautions.push('Más clics o mayor CTR no prueban ventas incrementales. Sin ingresos atribuidos no se calcula ROAS ni retorno de inversión.')
    model.checks.push('Compara plataformas por CTR y costo con bases suficientes; valida conversiones e ingresos atribuidos antes de reasignar presupuesto.')
  } else {
    model.subject = business ? 'Resultado y conexiones del negocio' : 'Ventas registradas'
    model.context = `${count(business?.alcance.filas_indicadores ?? m.kpis.transacciones)} registros incluidos en los indicadores. Los ingresos no equivalen a ganancia ni a dinero cobrado.`
    const specs = [
      ['ingresos', 'Ingresos', business ? business.estado_resultados.ventas_observadas : m.kpis.ingresos_totales?.valor, 'Suma de los ingresos incluidos después de aplicar exclusiones y filtros.'],
      ['costo', 'Costo conocido', business ? business.estado_resultados.costo_venta_conocido : m.kpis.gastos_totales?.valor, 'Costo disponible; no se imputa costo cero a las ventas sin correspondencia.'],
      ['utilidad', 'Utilidad sobre base con costo', business ? business.estado_resultados.utilidad_bruta : m.kpis.ganancia_neta?.valor, 'Ingresos pareados menos costos pareados; no equivale a utilidad neta del negocio.'],
    ] as const
    for (const [id, title, value, formula] of specs) {
      if (id !== 'ingresos' && !valid(value)) continue
      const measure = blankMeasure(id, title, value, 'moneda', formula)
      measure.series = business ? business.evolucion.map((row) => ({ period: row.mes, value: id === 'ingresos' ? row.ventas : id === 'costo' ? row.costo : row.utilidad_bruta, partial: row.parcial })) : m.evolucion_mensual.map((row) => ({ period: row.mes, value: id === 'ingresos' ? row.ingresos : id === 'costo' ? row.gastos ?? null : row.utilidad ?? null, partial: row.parcial }))
      const groupValue = (row: { ingresos: number; costo?: number | null; utilidad?: number | null }) => id === 'ingresos' ? row.ingresos : id === 'costo' ? row.costo ?? null : row.utilidad ?? null
      const rows = business ? Object.entries(business.agrupaciones) : [
        ['Categoría', m.por_categoria ?? []], ['Producto', m.top_productos ?? []], ['Canal / sucursal', m.ventas_por_canal ?? []],
        ...(m.agrupaciones_flexibles ?? []).map((row) => [row.columna, row.grupos_completos ?? row.grupos] as const),
      ] as Array<readonly [string, GroupRow[]]>
      measure.dimensions = rows.filter(([, groups]) => groups.length > 0).map(([name, groups]) => ({ name: label(name), groups: groups.map((row) => ({ name: row.nombre, value: groupValue(row), records: row.filas, coverage: row.cobertura_costos_pct })) }))
      if (id === 'ingresos' && m.matriz_mes_dimension) measure.movement = {
        dimension: label(m.matriz_mes_dimension.columna),
        values: m.matriz_mes_dimension.valores.map((row) => ({ period: row.mes, name: row.nombre, value: row.ingresos })),
      }
      model.measures.push(measure)
    }
    const coverage = business?.estado_resultados.cobertura_costos_pct ?? m.kpis.cobertura_costos?.pct
    if (coverage != null) model.cautions.push(`Cobertura de costos: ${count(coverage)}%. El margen solo describe la base con ingresos y costos pareados, no las ventas sin costo.`)
    else model.cautions.push('Sin costos pareados no se puede concluir rentabilidad; sin activos y pasivos corrientes tampoco se puede calcular liquidez.')
    const noDate = m.periodo.sin_fecha
    if (noDate?.filas) model.cautions.push(`${count(noDate.filas)} registros sin fecha${noDate.monto != null ? ` por ${money(noDate.monto)}` : ''}: ${noDate.excluidas_por_filtro ? 'excluidos por el filtro temporal' : 'incluidos en el total global, pero no en la serie mensual'}.`)
    const returns = m.kpis.devoluciones
    if (returns?.filas) model.cautions.push(`${count(returns.filas)} registros negativos por ${money(returns.monto)} afectan el neto; no se usan como participaciones de una distribución positiva.`)
    model.checks.push('Contrasta volumen, precio y devoluciones en los segmentos que cambian. Una diferencia de ventas no demuestra por sí sola qué la causó.')
  }

  if (business) {
    model.relations = business.calidad.integridad_referencial.map((row) => ({ name: row.relacion, rows: row.filas, matched: row.validas, unmatched: row.huerfanas, missing: row.sin_clave, coverage: row.cobertura_pct }))
    for (const decision of business.decisiones.slice(0, 3)) model.checks.push(`${decision.titulo}: ${decision.evidencia} Comprobación: ${decision.accion}`)
    if (business.calidad.filas_inconsistentes_formula > 0) model.cautions.push(`${count(business.calidad.filas_inconsistentes_formula)} filas no concilian con los controles de fórmula del libro.`)
    if (business.alcance.documentos_repetidos > 0) model.cautions.push(`${count(business.alcance.documentos_repetidos)} líneas de negocio repetidas; un documento con varios productos no es por sí solo un duplicado.`)
    if (business.alcance.documentos_conflictivos > 0) model.cautions.push(`${count(business.alcance.documentos_conflictivos)} documentos tienen información en conflicto; comprueba las versiones antes de certificar el resultado.`)
  }
  if (!model.relations.length && m.analysis_provenance) {
    const source = m.analysis_provenance
    const join = source.join && typeof source.join === 'object' ? source.join as Record<string, unknown> : source
    if (typeof join.rows_before === 'number' && typeof join.filas_sin_correspondencia === 'number' && typeof join.coverage === 'number') {
      model.relations.push({ name: `${String(join.left_sheet ?? 'Origen')} / ${String(join.right_sheet ?? 'Referencia')}`, rows: join.rows_before, matched: join.rows_before - join.filas_sin_correspondencia, unmatched: join.filas_sin_correspondencia, missing: null, coverage: join.coverage * 100 })
      if (join.rows_after !== join.rows_before) model.cautions.push('El número de filas cambió al relacionar las hojas; revisa la cardinalidad antes de usar sumas agregadas.')
    }
  }
  const duplicates = m.duplicados
  if (duplicates?.conservados) model.cautions.push(`${count(duplicates.conservados)} duplicados conservados. Pueden repetir aportes en los totales; no se eliminaron sin tu decisión.`)
  model.cautions.push(...m.advertencias)
  model.cautions = [...new Set(model.cautions)]
  return model
}

export interface ExplorationReading { title: string; evidence: string; meaning: string; next: string }

export function explorationActions(measure: ExplorationMeasure, metrics: MetricsResult, dimension?: string, from?: string | null, to?: string | null): Array<{ title: string; evidence: string; action: string }> {
  const actions: Array<{ title: string; evidence: string; action: string }> = []
  const selected = measure.dimensions.find((row) => row.name === dimension) ?? measure.dimensions[0]
  const groups = selected?.groups.filter((row) => valid(row.value)).slice().sort((a, b) => b.value! - a.value!) ?? []
  const leader = groups[0]
  const fmt = (value: number | null) => explorationValue(value, measure.format, metrics.moneda)
  const activity = metrics.actividad_productos
  if (measure.id === 'ingresos' && activity?.productos.length) {
    const product = activity.productos[0]
    actions.push({ title: 'Revisar productos sin ventas recientes', evidence: product.nombre + ': ' + product.meses_sin_venta_observada + ' meses sin ventas positivas observadas al ' + activity.fecha_corte + '. Última venta: ' + product.ultima_venta + '.', action: 'Verifica stock, estacionalidad y cobertura del archivo; prueba precio o marketing antes de reducir reposición o reasignar presupuesto. No equivale a falta de demanda.' })
  }
  if (leader) {
    const referenceCost = Boolean(metrics.analisis_productos) && measure.id === 'costo'
    const profit = /utilidad|ganancia|margen|rentabilidad/i.test(measure.id + ' ' + measure.label)
    const expense = !profit && /costo|gasto|inversion/i.test(measure.id + ' ' + measure.label)
    const loss = groups.slice().reverse().find((row) => row.value! < 0)
    actions.push({ title: referenceCost ? 'Revisar costos de referencia' : expense ? 'Revisar costos o gastos destacados' : profit ? 'Comparar rentabilidad del grupo' : measure.id === 'ingresos' ? 'Priorizar una revisión comercial' : 'Comparar el grupo destacado', evidence: leader.name + ' registra ' + fmt(leader.value) + ' en ' + (selected?.name ?? 'el desglose') + '; es el mayor valor entre los grupos disponibles.', action: referenceCost ? 'Comprueba unidad, moneda y vigencia del costo de catálogo. No representa gasto realizado; relaciona cantidades vendidas por ID antes de decidir compras o precios.' : expense ? 'Contrasta volumen, contratos y necesidad del gasto antes de recortar; un importe alto no demuestra ineficiencia.' : profit ? 'Contrasta margen, volumen y cobertura de costos; una utilidad mayor no implica mayor margen ni caja disponible.' : measure.id === 'ingresos' ? 'Comprueba margen, disponibilidad y recurrencia antes de reforzar compras o promoción; más ingresos no garantizan más utilidad.' : 'Revisa el tamaño y la cobertura del grupo antes de atribuirle mejor desempeño.' })
    if (loss) actions.push({ title: 'Investigar valores negativos', evidence: loss.name + ': ' + fmt(loss.value) + '.', action: 'Contrasta devoluciones, descuentos, costos y ajustes. No elimines el registro ni cambies el signo sin comprobar el origen.' })
  }
  const movement = explainExploration(measure, metrics.moneda, dimension, from, to).find((row) => row.title.startsWith('Dónde se concentra'))
  if (movement) actions.push({ title: movement.title, evidence: movement.evidence, action: movement.next })
  const coverage = metrics.analisis_negocio?.estado_resultados?.cobertura_costos_pct ?? metrics.kpis.cobertura_costos?.pct
  if (coverage != null && coverage < 99.5 && (measure.id === 'ingresos' || measure.id === 'utilidad')) actions.push({ title: 'Completar costos antes de reinvertir', evidence: explorationValue(coverage, 'porcentaje', metrics.moneda) + ' de cobertura de costos.', action: 'Completa los costos por ID y vigencia antes de usar el margen para decidir qué producto financiar.' })
  if (!actions.length) actions.push({ title: 'Validar la base de la decisión', evidence: measure.formula, action: 'Comprueba unidad, fechas y registros disponibles antes de comparar resultados o asignar presupuesto.' })
  return actions.slice(0, 3)
}

export function explainExploration(measure: ExplorationMeasure, currency: string, dimension?: string, from?: string | null, to?: string | null): ExplorationReading[] {
  const output: ExplorationReading[] = []
  const fmt = (value: number | null) => explorationValue(value, measure.format, currency)
  const visible = measure.series.filter((row) => (!from || row.period.slice(0, 7) >= from.slice(0, 7)) && (!to || row.period.slice(0, 7) <= to.slice(0, 7)))
  const full = visible.filter((row) => {
    const startsMidMonth = from && from.slice(0, 7) === row.period && from.slice(8, 10) !== '01'
    const monthEnd = new Date(Date.UTC(Number(row.period.slice(0, 4)), Number(row.period.slice(5, 7)), 0)).getUTCDate()
    const endsMidMonth = to && to.slice(0, 7) === row.period && Number(to.slice(8, 10)) !== monthEnd
    return !row.partial && !startsMidMonth && !endsMidMonth && /^\d{4}-\d{2}$/.test(row.period) && valid(row.value)
  }).sort((a, b) => a.period.localeCompare(b.period))
  const current = full[full.length - 1]
  const previous = full[full.length - 2]
  const monthIndex = (value: string) => Number(value.slice(0, 4)) * 12 + Number(value.slice(5, 7))
  if (current && previous && monthIndex(current.period) - monthIndex(previous.period) === 1) {
    const delta = current.value! - previous.value!
    const pct = previous.value! > 0 ? `${explorationValue(delta / previous.value! * 100, 'porcentaje', currency)} respecto a la base anterior.` : 'No se calcula variación porcentual sobre una base cero o negativa.'
    output.push({ title: `Cambio entre ${previous.period} y ${current.period}`, evidence: `${measure.label}: de ${fmt(previous.value)} a ${fmt(current.value)}. Diferencia: ${fmt(delta)}. ${pct}`, meaning: 'Se comparan meses consecutivos sin cobertura parcial marcada. Un aumento no significa necesariamente una mejora: depende de si mide ingresos, costos o existencias.', next: 'Contrasta ambos períodos con el mismo alcance y revisa si el cambio se concentra en algunos grupos.' })
    if (measure.movement) {
      const before = measure.movement.values.filter((row) => row.period === previous.period)
      const after = measure.movement.values.filter((row) => row.period === current.period)
      // Only explain a total through groups when both monthly sums reconcile.
      const reconciles = (rows: typeof before, total: number) => rows.length > 0 && Math.abs(rows.reduce((sum, row) => sum + row.value, 0) - total) <= Math.max(0.05, Math.abs(total) * 1e-9)
      if (reconciles(before, previous.value!) && reconciles(after, current.value!)) {
        const totals = new Map<string, number>()
        for (const row of before) totals.set(row.name, (totals.get(row.name) ?? 0) - row.value)
        for (const row of after) totals.set(row.name, (totals.get(row.name) ?? 0) + row.value)
        const leaders = [...totals].sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 3)
        output.push({ title: `Dónde se concentra el cambio: ${measure.movement.dimension}`, evidence: leaders.map(([name, value]) => `${name}: ${value > 0 ? '+' : ''}${fmt(value)}`).join('; ') + '.', meaning: 'Estos son los mayores aportes absolutos a la diferencia entre los dos meses. Los desgloses concilian con ambos totales; describen dónde cambia el monto, no por qué ocurrió.', next: 'Revisa cantidades, precios y devoluciones de estos grupos para distinguir volumen, mezcla y ajustes.' })
      }
    }
  } else {
    output.push({ title: 'Comparación temporal no concluyente', evidence: visible.length ? 'No hay dos meses completos consecutivos y con valor disponible para esta medida.' : 'No hay una serie temporal disponible para esta medida.', meaning: 'No se infiere crecimiento, caída ni estacionalidad a partir de un corte aislado, una base incompleta o meses separados.', next: 'Contrasta fechas, cobertura y períodos equivalentes antes de evaluar la evolución.' })
  }
  const selected = measure.dimensions.find((row) => row.name === dimension) ?? measure.dimensions[0]
  const groups = selected?.groups.filter((row) => valid(row.value)).slice().sort((a, b) => b.value! - a.value!) ?? []
  if (selected && groups.length) {
    const first = groups[0]
    const last = groups[groups.length - 1]
    const negative = groups.some((row) => row.value! < 0)
    output.push({ title: `Diferencias por ${selected.name}`, evidence: `Entre los grupos disponibles, ${first.name} registra el mayor valor: ${fmt(first.value)}${groups.length > 1 ? `; ${last.name}, el menor: ${fmt(last.value)}` : ''}.`, meaning: `${selected.totalGroups && selected.totalGroups > groups.length ? `Se muestran ${groups.length} de ${selected.totalGroups} grupos; no es la distribución completa. ` : ''}${negative ? 'Hay valores negativos: los importes no se interpretan como porciones de un total positivo. ' : ''}Un total mayor puede reflejar más registros, no mejor rendimiento. No demuestra causalidad.`, next: 'Compara cantidad de registros y cobertura del grupo antes de priorizar acciones; verifica también la cola no mostrada.' })
  }
  if (visible.some((row) => row.partial)) output.push({ title: 'Cobertura temporal a revisar', evidence: `${visible.filter((row) => row.partial).length} período(s) con cobertura parcial o no certificada.`, meaning: 'Sus valores siguen visibles como evidencia, pero no se tratan como meses completos en la comparación.', next: 'Revisa la fecha del último registro y compara días equivalentes.' })
  return output
}
