import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  Calculator,
  CheckCircle2,
  CircleDollarSign,
  Link2,
  Package,
  Receipt,
  Scale,
  Target,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import Card from './ui/Card'
import Badge from './ui/Badge'
import AdaptiveIndicatorCatalog from './AdaptiveIndicatorCatalog'
import NominalCollectionDashboard from './NominalCollectionDashboard'
import {
  AXIS_INK,
  CATEGORICAL,
  CHART,
  GRID_STROKE,
  formatCLPCompact,
  formatMonthShort,
  truncateLabel,
} from '../lib/charts'
import { formatCLP, formatNumber } from '../lib/format'
import type { BusinessAnalysis, BusinessGroupRow } from '../lib/types'

type Variant = 'summary' | 'explore'

function money(value: number | null | undefined) {
  return value == null ? 'No disponible' : formatCLP(value)
}

function percent(value: number | null | undefined) {
  return value == null ? 'No disponible' : `${formatNumber(value)}%`
}

function numeric(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function certificationMeta(state: BusinessAnalysis['estado_certificacion']) {
  if (state === 'certified') {
    return {
      label: 'Resultado verificable',
      note: 'Las relaciones y coberturas permiten usar los indicadores como resultado final.',
      tone: 'green' as const,
      classes: 'border-green/30 bg-green/[0.07]',
    }
  }
  if (state === 'partial') {
    return {
      label: 'Resultado parcial',
      note: 'Los indicadores disponibles son útiles, pero todavía tienen cobertura incompleta.',
      tone: 'gold' as const,
      classes: 'border-gold/35 bg-gold/[0.08]',
    }
  }
  return {
    label: 'Requiere revisión',
    note: 'Hay duplicados, costos incompletos o conflictos que impiden certificar el resultado.',
    tone: 'coral' as const,
    classes: 'border-coral/30 bg-coral/[0.07]',
  }
}

type CertificationBlocker = {
  key: string
  label: string
  detail: string
  cta?: { to: string; label: string; state?: Record<string, unknown> }
}

/** Traduce el "por qué" de una confianza baja a problemas concretos, cada uno
 * con el lugar donde resolverlo. Sin inventar datos: solo explica y guía. */
function certificationBlockers(analysis: BusinessAnalysis): CertificationBlocker[] {
  const { alcance, estado_resultados: result, calidad } = analysis
  const blockers: CertificationBlocker[] = []

  if (alcance.documentos_repetidos > 0) {
    blockers.push({
      key: 'duplicados',
      label: `${formatNumber(alcance.documentos_repetidos)} línea(s) de negocio repetida(s)`,
      detail: 'Se comparó la identidad de cada línea (transacción o documento + producto); un documento con varios productos no se considera duplicado. Las filas se conservan hasta que confirmes una limpieza.',
      cta: { to: '/limpieza?revision=1', label: 'Revisar IDs repetidos' },
    })
  }
  if (alcance.documentos_conflictivos > 0) {
    blockers.push({
      key: 'conflictos',
      label: `${formatNumber(alcance.documentos_conflictivos)} documento(s) en conflicto`,
      detail: 'Un mismo documento trae datos que no coinciden entre filas (montos o fechas distintas). Hay que decidir cuál es la versión válida.',
      cta: { to: '/limpieza?revision=1', label: 'Revisar conflictos' },
    })
  }
  const invalidDates = alcance.filas_fecha_invalida ?? 0
  const outOfPeriodDates = alcance.filas_fuera_periodo_declarado ?? 0
  if (invalidDates > 0 || outOfPeriodDates > 0) {
    blockers.push({
      key: 'fechas-periodo',
      label: `${formatNumber(invalidDates + outOfPeriodDates)} venta(s) excluida(s) por fecha`,
      detail: `${formatNumber(invalidDates)} no tienen fecha válida y ${formatNumber(outOfPeriodDates)} quedan fuera del periodo declarado. Las fechas inválidas permanecen en el total global, pero no entran a gráficos mensuales ni costos por vigencia.`,
      cta: { to: '/limpieza?revision=1', label: 'Revisar fechas' },
    })
  }
  const coverage = result.cobertura_costos_certificable_pct
  if (coverage != null && coverage < 95) {
    blockers.push({
      key: 'costos',
      label: `Costos incompletos — ${formatNumber(coverage)}% de las ventas con costo`,
      detail: 'El resto de las ventas no tiene un costo relacionado, así que la utilidad y el margen salen de una base parcial. Relaciona la hoja de costos o productos, o asigna la columna de costo.',
      cta: { to: '/limpieza', label: 'Asignar costos', state: { openMapping: true, highlightRole: 'costo' } },
    })
  }
  const negativos = numeric(calidad.costos.negativos)
  if (negativos > 0) {
    blockers.push({
      key: 'costos_negativos',
      label: `${formatNumber(negativos)} costo(s) negativo(s)`,
      detail: 'Hay costos con valor negativo que distorsionan la utilidad. Conviene corregirlos en el archivo o en la limpieza.',
      cta: { to: '/limpieza?revision=1', label: 'Revisar costos' },
    })
  }
  if (calidad.filas_inconsistentes_formula > 0) {
    blockers.push({
      key: 'formula',
      label: `${formatNumber(calidad.filas_inconsistentes_formula)} fila(s) con fórmula que no cuadra`,
      detail: 'En esas filas, cantidad × precio no coincide con el total declarado. Conviene revisar esos registros.',
    })
  }
  if (calidad.referencias_problematicas > 0) {
    blockers.push({
      key: 'referencias',
      label: `${formatNumber(calidad.referencias_problematicas)} referencia(s) problemática(s)`,
      detail: 'Algunas filas apuntan a un producto o cliente que no existe en su tabla; quedan fuera del enriquecimiento.',
    })
  }
  return blockers
}

function blockerLocations(analysis: BusinessAnalysis, key: string): string[] {
  if (key === 'duplicados' || key === 'conflictos') {
    return (analysis.calidad.documentos ?? [])
      .filter((item) => key !== 'conflictos' || item.tipo === 'conflicto')
      .slice(0, 6)
      .map((item) => (
        `ID ${item.id}: ${item.ubicaciones.map((place) => `${place.hoja}, fila ${place.fila}`).join(' · ')}`
      ))
  }
  if (key === 'costos_negativos') {
    return (analysis.calidad.costos_detalle?.negativos ?? [])
      .slice(0, 8)
      .map((item) => (
        `${item.hoja ?? 'Hoja de costos'}, fila ${item.fila}: ${formatCLP(item.valor)}${
          item.clave ? ` · clave ${item.clave}` : ''
        }`
      ))
  }
  if (key === 'formula') {
    return analysis.calidad.controles_formula
      .filter((control) => control.filas_inconsistentes > 0)
      .slice(0, 8)
      .map((control) => (
        `${control.hoja}, ${control.control}: filas ${control.filas_ejemplo.join(', ')}`
      ))
  }
  if (key === 'referencias') {
    return analysis.calidad.integridad_referencial
      .filter((relation) => relation.huerfanas > 0 || relation.sin_clave > 0)
      .slice(0, 8)
      .map((relation) => {
        const locations = (relation.ubicaciones ?? [])
          .slice(0, 4)
          .map((place) => `${place.hoja}, fila ${place.fila}`)
          .join(' · ')
        return `${relation.relacion}: ${formatNumber(relation.huerfanas)} huérfanas${
          locations ? ` · ${locations}` : ` · ejemplos ${relation.ejemplos.join(', ')}`
        }`
      })
  }
  return []
}

/** Diagnóstico del análisis cruzado. Vive en Limpieza porque orienta la
 * revisión de datos; Resumen queda reservado para indicadores del negocio. */
export function BusinessQualityPanel({ analysis }: { analysis: BusinessAnalysis }) {
  const certification = certificationMeta(analysis.estado_certificacion)
  const blockers = certificationBlockers(analysis)
  return (
    <section className={`rounded-lg border px-4 py-4 ${certification.classes}`}>
      <div className="flex items-start gap-3">
        {analysis.estado_certificacion === 'certified' ? (
          <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-green" />
        ) : (
          <AlertTriangle className={`mt-0.5 h-5 w-5 shrink-0 ${analysis.estado_certificacion === 'blocked' ? 'text-coral' : 'text-gold'}`} />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-navy">Calidad del análisis relacionado</h2>
            <Badge tone={certification.tone}>{certification.label}</Badge>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-navy/65">
            {certification.note} Confianza técnica: {formatNumber(analysis.confianza_pct)}%.
            Los hallazgos se muestran para revisión; no se borran ni corrigen automáticamente.
          </p>
        </div>
      </div>
      {blockers.length > 0 && (
        <ul className="mt-4 grid gap-3 lg:grid-cols-2">
          {blockers.map((blocker) => {
            const locations = blockerLocations(analysis, blocker.key)
            return (
              <li key={blocker.key} className="rounded-lg border border-navy/10 bg-white/80 p-3">
                <p className="text-xs font-semibold text-navy">{blocker.label}</p>
                <p className="mt-1 text-[11px] leading-relaxed text-navy/60">{blocker.detail}</p>
                {locations.length > 0 && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-[11px] font-semibold text-teal">
                      Ver hojas y filas de ejemplo
                    </summary>
                    <ul className="mt-2 space-y-1 text-[11px] text-navy/65">
                      {locations.map((location) => <li key={location}>{location}</li>)}
                    </ul>
                  </details>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function BusinessTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-navy/10 bg-white px-3 py-2 text-xs shadow-lg">
      {label && <p className="mb-1 font-semibold text-navy">{formatMonthShort(label)}</p>}
      {payload.map((item) => (
        <p key={item.name} className="flex items-center justify-between gap-4 text-navy/70">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
            {item.name}
          </span>
          <strong className="text-navy">{formatCLP(item.value)}</strong>
        </p>
      ))}
    </div>
  )
}

function ExecutiveSummary({ analysis }: { analysis: BusinessAnalysis }) {
  const result = analysis.estado_resultados
  const operation = analysis.operacion
  const usesEstimatedCosts = result.costo_venta_estimado_catalogo > 0
  const provisionalProfitability =
    result.cobertura_costos_certificable_pct < 99.5 ||
    analysis.estado_certificacion !== 'certified'
  const operatingExpenseLabel = result.base_gastos_operacionales === 'monto_neto'
    ? 'gastos operacionales netos (IVA separado)'
    : 'gastos operacionales'
  // Un mes parcial nunca se compara por total contra un mes completo. Las
  // tarjetas usan los dos últimos meses completos y el parcial se explica por
  // ritmo diario, con su proyección claramente etiquetada como estimación.
  const completeEvolution = analysis.evolucion.filter((row) => !row.parcial)
  const latest = completeEvolution[completeEvolution.length - 1]
  const previous = completeEvolution[completeEvolution.length - 2]
  const partialMonth = [...analysis.evolucion].reverse().find((row) => row.parcial)
  const partialSalesComparison = (
    partialMonth?.variacion_ritmo_pct != null
    && partialMonth.ritmo_diario_ventas != null
  )
    ? `Mes parcial (${partialMonth.cobertura_hasta_dia}/${partialMonth.dias_del_mes} días): ritmo diario ${
        partialMonth.variacion_ritmo_pct >= 0 ? '↑' : '↓'
      } ${formatNumber(Math.abs(partialMonth.variacion_ritmo_pct))}%`
    : null
  const compare = (current: number | null | undefined, prior: number | null | undefined) => {
    if (current == null || prior == null) return 'Sin periodo anterior comparable'
    const nominal = current - prior
    const variation = prior === 0 ? null : (nominal / Math.abs(prior)) * 100
    return `${nominal >= 0 ? '↑' : '↓'} ${money(Math.abs(nominal))}${
      variation == null ? '' : ` · ${formatNumber(Math.abs(variation))}%`
    } vs mes anterior`
  }
  const compareMargin = (
    currentProfit: number | null | undefined,
    currentSales: number | null | undefined,
    previousProfit: number | null | undefined,
    previousSales: number | null | undefined,
  ) => {
    if (
      currentProfit == null || currentSales == null || currentSales === 0
      || previousProfit == null || previousSales == null || previousSales === 0
    ) return 'Sin periodo anterior comparable'
    const delta = (currentProfit / currentSales - previousProfit / previousSales) * 100
    return `${delta >= 0 ? '↑' : '↓'} ${formatNumber(Math.abs(delta))} pp vs mes anterior`
  }
  const certification = analysis.estado_certificacion === 'certified'
    ? 'Certificado'
    : analysis.estado_certificacion === 'partial'
      ? 'Parcial'
      : 'No certificado'
  const cards = [
    {
      label: 'Ventas netas observadas',
      value: money(result.ventas_observadas),
      detail: analysis.alcance.documentos_repetidos > 0
        ? `${formatNumber(analysis.alcance.documentos_repetidos)} línea(s) repetida(s) señaladas, sin alterar el total`
        : `${formatNumber(analysis.alcance.filas_indicadores)} filas incluidas`,
      icon: CircleDollarSign,
      color: CHART.ingresos,
      comparison: partialSalesComparison ?? compare(latest?.ventas, previous?.ventas),
      state: certification,
    },
    {
      label: 'Costo de ventas histórico',
      value: money(result.costo_venta_conocido),
      detail: usesEstimatedCosts
        ? `${percent(result.cobertura_costos_historica_pct)} con vigencia; el catálogo actual se informa aparte`
        : `${percent(result.cobertura_costos_pct)} de cobertura histórica`,
      icon: Receipt,
      color: CHART.gastos,
      comparison: compare(latest?.costo, previous?.costo),
      state: result.cobertura_costos_historica_pct >= 99.5 ? certification : 'Parcial',
    },
    {
      label: 'Utilidad bruta histórica',
      value: money(result.utilidad_bruta),
      detail: usesEstimatedCosts
        ? `${percent(result.cobertura_costos_historica_pct)} con vigencia; el relleno actual se informa aparte`
        : 'ventas pareadas − costo de ventas histórico',
      icon: TrendingUp,
      color: CHART.utilidad,
      comparison: compare(latest?.utilidad_bruta, previous?.utilidad_bruta),
      state: provisionalProfitability ? 'Parcial' : certification,
    },
    {
      label: provisionalProfitability ? 'Margen bruto · base histórica' : 'Margen bruto',
      value: percent(result.margen_bruto_pct),
      detail: 'solo ventas con costo relacionado',
      icon: Scale,
      color: CHART.flujo,
      comparison: compareMargin(
        latest?.utilidad_bruta,
        latest?.ventas,
        previous?.utilidad_bruta,
        previous?.ventas,
      ),
      state: provisionalProfitability ? 'Parcial' : certification,
    },
    {
      label: 'Gastos operativos',
      value: money(result.gastos_operacionales_periodo ?? result.gastos_operacionales),
      detail: result.filas_gastos > 0
        ? `${formatNumber(result.filas_gastos)} registros comparables`
        : 'Conecta una hoja de gastos operacionales',
      icon: Wallet,
      color: CATEGORICAL[2],
      comparison: compare(latest?.gastos_operacionales, previous?.gastos_operacionales),
      state: result.gastos_operacionales == null ? 'Dato faltante' : certification,
    },
    {
      label: 'Utilidad operacional',
      value: money(result.resultado_operacional),
      detail: result.margen_operacional_pct == null
        ? 'sin ventas, costos y gastos comparables suficientes'
        : `ventas − costo de venta − ${operatingExpenseLabel} · margen ${percent(result.margen_operacional_pct)}`,
      icon: Wallet,
      color: CHART.alerta,
      comparison: compare(latest?.resultado_operacional, previous?.resultado_operacional),
      state: result.resultado_operacional == null ? 'Dato faltante' : certification,
    },
    {
      label: 'Cuentas por cobrar',
      value: money(operation.cuentas_por_cobrar),
      detail: operation.cuentas_vencidas == null
        ? 'sin cartera relacionable'
        : `${money(operation.cuentas_vencidas)} vencido · DSO ${operation.dso_dias == null ? '—' : `${formatNumber(operation.dso_dias)} días`}`,
      icon: Receipt,
      color: CHART.gastos,
      comparison: operation.mora_promedio_dias == null
        ? 'Sin antigüedad de mora comparable'
        : `${formatNumber(operation.mora_promedio_dias)} días de mora promedio`,
      state: operation.cuentas_por_cobrar == null ? 'Dato faltante' : certification,
    },
    {
      label: 'Inventario valorizado',
      value: money(operation.valor_inventario),
      detail: operation.rotacion_inventario_aprox == null
        ? operation.fecha_corte_inventario
          ? `corte ${operation.fecha_corte_inventario}`
          : 'sin corte valorizable'
        : `${formatNumber(operation.rotacion_inventario_aprox)}x · corte ${operation.fecha_corte_inventario ?? 'disponible'}`,
      icon: Package,
      color: CATEGORICAL[3],
      comparison: operation.inventario_bajo_minimo == null
        ? 'Sin mínimo de inventario comparable'
        : `${formatNumber(operation.inventario_bajo_minimo)} registros bajo mínimo`,
      state: operation.valor_inventario == null ? 'Dato faltante' : certification,
    },
    ...(result.ebitda != null
      ? [{
          label: 'EBITDA',
          value: money(result.ebitda),
          detail: `resultado operacional + ${money(result.depreciacion_amortizacion)} de depreciación/amortización`,
          icon: Wallet,
          color: CATEGORICAL[4],
          comparison: 'Calculado sólo con partidas presentes en el libro',
          state: certification,
        }]
      : []),
    ...(analysis.metas.metas_evaluadas
      ? [{
          label: 'Metas cumplidas',
          value: `${formatNumber(analysis.metas.metas_cumplidas ?? 0)} de ${formatNumber(analysis.metas.metas_evaluadas)}`,
          detail: 'comparadas por mes y sucursal',
          icon: Target,
          color: CATEGORICAL[5],
          comparison: analysis.metas.cumplimiento_pct == null
            ? 'Sin cumplimiento global comparable'
            : `${percent(analysis.metas.cumplimiento_pct)} de la meta de ventas`,
          state: certification,
        }]
      : []),
  ]
  const availableRatios = analysis.ratios.filter((ratio) => ratio.estado !== 'unavailable')
  const monthlyProfitability = analysis.evolucion
    .filter((row) => row.utilidad_bruta != null)
    .map((row) => ({
      ...row,
      margen_pct:
        row.ventas > 0 && row.utilidad_bruta != null
          ? (row.utilidad_bruta / row.ventas) * 100
          : null,
    }))
  const qualityIssueCount = certificationBlockers(analysis).length
  const usableContributions = (
    rows: BusinessAnalysis['agrupaciones'][string] = [],
  ) => rows.filter((row) => (
    row.utilidad != null
    && row.nombre.trim().toLocaleLowerCase('es-CL') !== 'sin clasificar'
    && (row.participacion_pct ?? 0) < 99.95
  ))
  // Para una conclusión ejecutiva se prioriza categoría, luego producto y
  // sucursal. Mezclar las tres listas podía elegir un grupo artificial o
  // repetir el total completo como “Sin clasificar”.
  const contributionRows = [
    usableContributions(analysis.agrupaciones.categorias),
    usableContributions(analysis.agrupaciones.productos),
    usableContributions(analysis.agrupaciones.sucursales),
  ].find((rows) => rows.length > 0) ?? []
  const topContribution = [...contributionRows]
    .sort((left, right) => (right.utilidad ?? 0) - (left.utilidad ?? 0))[0]
  const latestSalesChange = latest && previous && previous.ventas !== 0
    ? ((latest.ventas - previous.ventas) / Math.abs(previous.ventas)) * 100
    : null
  const partialConclusion = partialMonth?.variacion_ritmo_pct != null
    ? `${formatMonthShort(partialMonth.mes)} está parcial (${partialMonth.cobertura_hasta_dia} de ${partialMonth.dias_del_mes} días): el ritmo diario ${
        partialMonth.variacion_ritmo_pct >= 0 ? 'creció' : 'cayó'
      } ${formatNumber(Math.abs(partialMonth.variacion_ritmo_pct))}% frente al mes completo anterior${
        partialMonth.proyeccion_ritmo_mes_completo != null
          ? `; al mismo ritmo cerraría cerca de ${money(partialMonth.proyeccion_ritmo_mes_completo)} (estimación)`
          : ''
      }.`
    : null
  const conclusions = [
    partialConclusion ?? (
      latestSalesChange == null
        ? 'No existe un periodo anterior completo para medir crecimiento.'
        : `Las ventas del último mes completo ${latestSalesChange >= 0 ? 'crecieron' : 'cayeron'} ${formatNumber(Math.abs(latestSalesChange))}% frente al mes completo anterior.`
    ),
    result.utilidad_bruta == null
      ? 'No se puede explicar el cambio en utilidad hasta completar la relación de costos.'
      : `La utilidad bruta conocida es ${money(result.utilidad_bruta)} con margen de ${percent(result.margen_bruto_pct)}.`,
    topContribution
      ? `${topContribution.nombre} es el mayor aporte identificable a la utilidad conocida (${money(topContribution.utilidad)}).`
      : 'No hay una dimensión con costo pareado suficiente para atribuir la utilidad.',
    qualityIssueCount > 0
      ? `${formatNumber(qualityIssueCount)} alerta(s) pueden afectar la certificación de los indicadores.`
      : 'No hay bloqueos de certificación pendientes en este análisis.',
    result.cobertura_costos_certificable_pct < 95
      ? `La principal oportunidad es elevar la cobertura de costos desde ${percent(result.cobertura_costos_certificable_pct)}.`
      : 'La cobertura de costos permite comparar la rentabilidad con una base amplia.',
  ]

  return (
    <div className="space-y-6">
      <section className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-4">
        {cards.map(({ label, value, detail, icon: Icon, color, comparison, state }) => (
          <Card
            key={label}
            className="!p-4"
            style={{ background: `linear-gradient(145deg, ${color}16, #ffffff 66%)` }}
          >
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full" style={{ background: `${color}1c` }}>
                <Icon className="h-4 w-4" style={{ color }} />
              </span>
              <p className="text-xs font-medium text-navy/55">{label}</p>
            </div>
            <p className="mt-3 break-words text-xl font-bold leading-tight text-navy">{value}</p>
            <p className="mt-1 text-[11px] leading-relaxed text-navy/50">{detail}</p>
            <p className="mt-2 text-[10px] font-medium text-navy/55">{comparison}</p>
            <span className={[
              'mt-2 inline-flex rounded-full px-2 py-0.5 text-[9px] font-semibold',
              state === 'Certificado'
                ? 'bg-green/10 text-green'
                : state === 'Dato faltante' || state === 'No certificado'
                  ? 'bg-coral/10 text-coral'
                  : 'bg-gold/15 text-amber-700',
            ].join(' ')}>
              {state}
            </span>
          </Card>
        ))}
      </section>

      {qualityIssueCount > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gold/30 bg-gold/[0.07] px-4 py-3">
          <p className="text-xs leading-relaxed text-navy/70">
            Hay {formatNumber(qualityIssueCount)} alerta(s) que podrían afectar algunos indicadores.
          </p>
          <Link
            to="/alertas"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-teal hover:text-navy"
          >
            Ver alertas <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      )}

      <AdaptiveIndicatorCatalog analysis={analysis} />

      <div data-testid="business-summary-flow" className="grid items-start gap-6 xl:grid-cols-2">
        {analysis.evolucion.length > 0 && (
          <Card id="business-trend" className="min-w-0 xl:col-span-2">
            <h2 className="text-base font-semibold text-navy">Evolución del negocio</h2>
            <p className="mt-1 text-xs text-navy/55">
              Resultado operacional = ventas − costo de venta relacionado − {operatingExpenseLabel} del periodo. Los gastos sin fecha válida quedan fuera del cálculo y los vacíos no se convierten en cero.
            </p>
            <div className="mt-4 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={analysis.evolucion} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
                  <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                  <XAxis dataKey="mes" tickFormatter={formatMonthShort} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 10 }} width={64} axisLine={false} tickLine={false} />
                  <Tooltip content={<BusinessTooltip />} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="ventas" name="Ventas" fill={CHART.ingresos} radius={[3, 3, 0, 0]} maxBarSize={24} fillOpacity={0.85} />
                  <Bar dataKey="costo" name="Costo relacionado" fill={CHART.gastos} radius={[3, 3, 0, 0]} maxBarSize={24} fillOpacity={0.85} />
                  {/* Resultado operacional en coral y más grueso: es la línea clave
                      y debe leerse por encima de las barras de ventas/costo. */}
                  <Line type="monotone" dataKey="resultado_operacional" name="Resultado operacional" stroke={CHART.alerta} strokeWidth={3.25} dot={{ r: 3, strokeWidth: 1.5, stroke: '#ffffff', fill: CHART.alerta }} activeDot={{ r: 5 }} connectNulls={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Card>
        )}

        <Card id="business-profitability" className="min-w-0">
          <div className="flex items-center gap-2">
            <Target className="h-4.5 w-4.5 text-gold" />
            <h2 className="text-base font-semibold text-navy">Metas y punto de equilibrio</h2>
          </div>
          {analysis.metas.disponible && analysis.metas.cumplimiento_pct != null ? (
            <>
              <div className="mt-4 flex items-end justify-between gap-3">
                <div>
                  <p className="text-xs text-navy/50">Cumplimiento de ventas</p>
                  <p className="text-3xl font-bold text-navy">{percent(analysis.metas.cumplimiento_pct)}</p>
                </div>
                <p className="text-right text-xs text-navy/55">
                  {money(analysis.metas.venta_comparable)}<br />de {money(analysis.metas.meta_venta)}
                </p>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-navy/10">
                <div
                  className="h-full rounded-full bg-gold"
                  style={{ width: `${Math.min(Math.max(analysis.metas.cumplimiento_pct, 0), 100)}%` }}
                />
              </div>
            </>
          ) : (
            <p className="mt-4 text-sm text-navy/55">No hay metas mensuales comparables en el libro.</p>
          )}
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg bg-navy/[0.04] px-3 py-3">
              <p className="text-[11px] text-navy/50">Punto de equilibrio del periodo</p>
              <p className="mt-1 text-sm font-semibold text-navy">{money(operation.punto_equilibrio_ventas)}</p>
            </div>
            <div className="rounded-lg bg-teal/[0.06] px-3 py-3">
              <p className="text-[11px] text-navy/50">Gasto fijo mensual promedio</p>
              <p className="mt-1 text-sm font-semibold text-navy">{money(operation.gasto_fijo_mensual_promedio)}</p>
            </div>
          </div>
        </Card>

        <Card className="min-w-0">
          <div className="flex items-center gap-2">
            <Calculator className="h-4.5 w-4.5 text-teal" />
            <h2 className="text-base font-semibold text-navy">Indicadores disponibles</h2>
          </div>
          <ul className="mt-3 divide-y divide-navy/5">
            {availableRatios.map((ratio) => (
              <li key={ratio.id} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-navy">{ratio.nombre}</p>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-navy/50">{ratio.nota}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-sm font-bold text-navy">{formatRatioValue(ratio.id, ratio.valor)}</p>
                  <Badge tone={ratio.estado === 'available' ? 'green' : 'gold'}>
                    {ratio.estado === 'available' ? 'Disponible' : 'Parcial'}
                  </Badge>
                </div>
              </li>
            ))}
          </ul>
          {availableRatios.length === 0 && (
            <p className="mt-3 text-sm text-navy/55">No hay ratios con base suficiente.</p>
          )}
        </Card>

        <Card className="min-w-0 xl:col-span-2">
          <h2 className="text-base font-semibold text-navy">Utilidad y margen mensual</h2>
          <p className="mt-1 text-xs text-navy/55">
            Compara cuánto quedó después del costo de venta y qué porcentaje representa sobre las ventas relacionadas.
          </p>
          {monthlyProfitability.length > 0 ? (
            <div className="mt-4 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={monthlyProfitability} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                  <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                  <XAxis dataKey="mes" tickFormatter={formatMonthShort} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis yAxisId="money" tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 10 }} width={64} axisLine={false} tickLine={false} />
                  <YAxis yAxisId="margin" orientation="right" tickFormatter={(value) => `${formatNumber(value)}%`} tick={{ fill: AXIS_INK, fontSize: 10 }} width={42} axisLine={false} tickLine={false} />
                  <Tooltip
                    formatter={(value, name) => (
                      String(name).startsWith('Margen bruto')
                        ? `${formatNumber(Number(value))}%`
                        : formatCLP(Number(value))
                    )}
                    labelFormatter={(label) => formatMonthShort(String(label))}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <ReferenceLine yAxisId="money" y={0} stroke={AXIS_INK} strokeOpacity={0.45} />
                  <Bar yAxisId="money" dataKey="utilidad_bruta" name="Utilidad bruta histórica" fill={CHART.utilidad} radius={[4, 4, 0, 0]} maxBarSize={36} />
                  <Line yAxisId="margin" type="monotone" dataKey="margen_pct" name="Margen bruto histórico" stroke={CHART.flujo} strokeWidth={2.5} dot={{ r: 3 }} connectNulls={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="mt-4 text-sm text-navy/55">No hay costos relacionados suficientes para calcular utilidad mensual.</p>
          )}
        </Card>
      </div>
      <Card id="business-conclusions">
        <h2 className="text-base font-semibold text-navy">Conclusiones del periodo</h2>
        <p className="mt-1 text-xs text-navy/55">
          Resultados deterministas sobre la información disponible; los datos parciales se indican expresamente.
        </p>
        <ol className="mt-4 grid gap-3 md:grid-cols-2 2xl:grid-cols-5">
          {conclusions.map((conclusion, index) => (
            <li key={conclusion} className="rounded-lg border border-navy/10 bg-navy/[0.025] p-3">
              <span className="text-[10px] font-bold uppercase tracking-wide text-teal">
                Conclusión {index + 1}
              </span>
              <p className="mt-1 text-xs leading-relaxed text-navy/70">{conclusion}</p>
              {index < 3 ? (
                <a
                  href={index === 0 ? '#business-trend' : '#business-profitability'}
                  className="mt-2 inline-flex text-[11px] font-semibold text-teal hover:underline"
                >
                  Abrir gráfico
                </a>
              ) : (
                <Link
                  to="/alertas"
                  className="mt-2 inline-flex text-[11px] font-semibold text-teal hover:underline"
                >
                  Abrir detalle
                </Link>
              )}
            </li>
          ))}
        </ol>
      </Card>
    </div>
  )
}

function formatRatioValue(id: string, value: number | null) {
  if (value == null) return 'No disponible'
  if (id.includes('margen') || id.includes('tasa') || id.includes('cumplimiento')) {
    return percent(value)
  }
  if (id.includes('rotacion')) return `${formatNumber(value)}x`
  return money(value)
}

function ProfitabilityChart({ rows }: { rows: BusinessGroupRow[] }) {
  const data = rows
    .filter((row) => row.utilidad != null)
    .slice(0, 10)
    .map((row) => ({ ...row, etiqueta: truncateLabel(row.nombre, 20) }))
  if (!data.length) return <p className="mt-4 text-sm text-navy/55">No hay cobertura suficiente para comparar utilidad.</p>
  return (
    <div className="mt-4" style={{ height: Math.max(280, data.length * 36 + 48) }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 8 }}>
          <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
          <XAxis type="number" tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey="etiqueta" width={130} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
          <Tooltip formatter={(value) => formatCLP(Number(value))} />
          <ReferenceLine x={0} stroke={AXIS_INK} />
          <Bar dataKey="utilidad" name="Utilidad conocida" fill={CHART.utilidad} radius={[0, 3, 3, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function DiagnosticAnalysis({ analysis }: { analysis: BusinessAnalysis }) {
  const costQuality = analysis.calidad.costos
  const problematicCosts = numeric(costQuality.negativos) + numeric(costQuality.ceros) + numeric(costQuality.extremos)
  const sensitivityRows = [
    { escenario: 'Costo actual', utilidad: analysis.sensibilidad.base_utilidad_bruta },
    { escenario: 'Costo +5%', utilidad: analysis.sensibilidad.costo_mas_5 },
    { escenario: 'Costo +10%', utilidad: analysis.sensibilidad.costo_mas_10 },
  ].filter((row): row is { escenario: string; utilidad: number } => row.utilidad != null)
  const products = analysis.agrupaciones.productos ?? []
  const unavailable = analysis.ratios.filter((ratio) => ratio.estado === 'unavailable')

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-navy/15 bg-navy/[0.035] px-4 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-navy/45">Explorar · entender causas</p>
        <p className="mt-1 text-sm text-navy/70">
          Aquí no repetimos el tablero: explicamos qué limita el resultado, dónde se concentra y qué decisión revisar primero.
        </p>
      </section>

      <div className="grid items-start gap-6 xl:grid-cols-2">
        <Card className="min-w-0">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4.5 w-4.5 text-green" />
            <h2 className="text-base font-semibold text-navy">Qué productos explican la utilidad</h2>
          </div>
          <p className="mt-1 text-xs text-navy/55">Comparación sobre ventas con costo relacionado, sin rellenar faltantes con cero.</p>
          <ProfitabilityChart rows={products} />
        </Card>

        <Card className="min-w-0">
          <div className="flex items-center gap-2">
            <Scale className="h-4.5 w-4.5 text-coral" />
            <h2 className="text-base font-semibold text-navy">Sensibilidad al costo</h2>
          </div>
          <p className="mt-1 text-xs text-navy/55">Impacto mecánico si el costo conocido sube y ventas/volumen permanecen iguales.</p>
          {sensitivityRows.length > 0 ? (
            <div className="mt-4 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sensitivityRows} margin={{ top: 12, right: 12, bottom: 4, left: 8 }}>
                  <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                  <XAxis dataKey="escenario" tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 10 }} width={64} axisLine={false} tickLine={false} />
                  <Tooltip formatter={(value) => formatCLP(Number(value))} />
                  <ReferenceLine y={0} stroke={AXIS_INK} />
                  <Bar dataKey="utilidad" name="Utilidad bruta" fill={CHART.alerta} radius={[4, 4, 0, 0]} maxBarSize={52} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="mt-4 text-sm text-navy/55">No hay costo pareado suficiente para simular escenarios.</p>
          )}
          <p className="mt-2 text-[11px] leading-relaxed text-navy/45">{analysis.sensibilidad.nota}</p>
        </Card>
      </div>

      <section className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(300px,.75fr)]">
        <Card className="min-w-0">
          <div className="flex items-center gap-2">
            <Link2 className="h-4.5 w-4.5 text-teal" />
            <h2 className="text-base font-semibold text-navy">Calidad de las relaciones</h2>
          </div>
          <p className="mt-1 text-xs text-navy/55">Una referencia huérfana queda fuera del enriquecimiento; nunca multiplica ventas ni se une a ciegas.</p>
          <div className="mt-4 space-y-3 sm:hidden">
            {analysis.calidad.integridad_referencial.map((row) => (
              <div key={row.relacion} className="rounded-lg bg-navy/[0.04] px-3 py-3 text-xs">
                <p className="font-semibold text-navy">{row.relacion}</p>
                <p className="mt-1 text-navy/60">Cobertura {percent(row.cobertura_pct)} · {formatNumber(row.huerfanas)} huérfanas · {formatNumber(row.sin_clave)} sin clave</p>
              </div>
            ))}
          </div>
          <div className="mt-4 hidden overflow-x-auto sm:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-navy/10 text-left text-[11px] uppercase text-navy/45">
                  <th className="pb-2 pr-4">Relación</th>
                  <th className="pb-2 pr-4 text-right">Cobertura</th>
                  <th className="pb-2 pr-4 text-right">Huérfanas</th>
                  <th className="pb-2 text-right">Sin clave</th>
                </tr>
              </thead>
              <tbody>
                {analysis.calidad.integridad_referencial.map((row) => (
                  <tr key={row.relacion} className="border-b border-navy/5">
                    <td className="py-2.5 pr-4 font-medium text-navy">{row.relacion}</td>
                    <td className="py-2.5 pr-4 text-right text-navy/70">{percent(row.cobertura_pct)}</td>
                    <td className="py-2.5 pr-4 text-right text-navy/70">{formatNumber(row.huerfanas)}</td>
                    <td className="py-2.5 text-right text-navy/70">{formatNumber(row.sin_clave)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <div className="space-y-6">
          <Card>
            <h2 className="text-base font-semibold text-navy">Controles de calidad</h2>
            <dl className="mt-3 space-y-3 text-sm">
              <QualityLine label="Referencias problemáticas" value={analysis.calidad.referencias_problematicas} />
              <QualityLine label="Fórmulas que no cuadran" value={analysis.calidad.filas_inconsistentes_formula} />
              <QualityLine label="Costos a revisar" value={problematicCosts} />
              <QualityLine label="Documentos sobrepagados" value={analysis.operacion.documentos_sobrepagados} />
              <QualityLine label="Pagos duplicados excluidos" value={analysis.operacion.pagos_duplicados_excluidos} />
            </dl>
          </Card>
          {unavailable.length > 0 && (
            <Card>
              <div className="flex items-center gap-2">
                <Calculator className="h-4.5 w-4.5 text-navy/55" />
                <h2 className="text-base font-semibold text-navy">Qué falta para otros ratios</h2>
              </div>
              <ul className="mt-3 space-y-3">
                {unavailable.map((ratio) => (
                  <li key={ratio.id}>
                    <p className="text-sm font-medium text-navy">{ratio.nombre}</p>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-navy/50">{ratio.nota}</p>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </section>

      {analysis.portafolio.productos.length > 0 && (
        <Card>
          <h2 className="text-base font-semibold text-navy">Portafolio: volumen y margen</h2>
          <p className="mt-1 text-xs text-navy/55">Clasificación relativa frente a las medianas del propio archivo.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {(['estrella', 'vaca_lechera', 'oportunidad', 'problema'] as const).map((quadrant, index) => {
              const rows = analysis.portafolio.productos.filter((row) => row.cuadrante === quadrant)
              const labels = {
                estrella: 'Alto volumen y margen',
                vaca_lechera: 'Volumen alto, margen bajo',
                oportunidad: 'Margen alto, volumen bajo',
                problema: 'Volumen y margen bajos',
              }
              return (
                <div key={quadrant} className="rounded-lg border border-navy/10 bg-work px-3 py-3">
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: CATEGORICAL[index] }} />
                    <p className="text-xs font-semibold text-navy">{labels[quadrant]}</p>
                  </div>
                  <p className="mt-1 text-[11px] text-navy/50">{formatNumber(rows.length)} producto(s)</p>
                  <p className="mt-2 line-clamp-3 text-[11px] leading-relaxed text-navy/65">
                    {rows.slice(0, 4).map((row) => row.nombre).join(' · ') || 'Sin productos en este cuadrante'}
                  </p>
                </div>
              )
            })}
          </div>
        </Card>
      )}
    </div>
  )
}

function QualityLine({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-navy/5 pb-2 last:border-0 last:pb-0">
      <dt className="text-navy/65">{label}</dt>
      <dd className={`font-semibold ${value > 0 ? 'text-coral' : 'text-green'}`}>{formatNumber(value)}</dd>
    </div>
  )
}

export default function BusinessAnalysisPanel({
  analysis,
  variant,
}: {
  analysis: BusinessAnalysis
  variant: Variant
}) {
  if (analysis.perfil === 'cobranza_nominal' && analysis.cobranza) {
    return <NominalCollectionDashboard analysis={analysis} variant={variant} />
  }
  return variant === 'summary'
    ? <ExecutiveSummary analysis={analysis} />
    : <DiagnosticAnalysis analysis={analysis} />
}
