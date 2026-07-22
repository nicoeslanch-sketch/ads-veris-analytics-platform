import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import Card from './ui/Card'
import { AXIS_INK, CHART, GRID_STROKE, formatCLPCompact, formatMonthShort, truncateLabel } from '../lib/charts'
import { formatCLP, formatNumber } from '../lib/format'
import type { MetricsResult } from '../lib/types'

/** Fase 19 — Explorar interpreta; el Resumen muestra los números.
 *
 * Clasificación de portafolio (participación × margen contra las MEDIANAS del
 * propio archivo), productos con margen negativo, ventas bajo costo y la
 * evolución del margen mes a mes — cada bloque dice qué decisión gatilla. */

type Rentabilidad = NonNullable<MetricsResult['analisis_rentabilidad']>
type Producto = Rentabilidad['clasificacion_productos'][number]

const CUADRANTES: Record<Producto['cuadrante'], { titulo: string; color: string; accion: string }> = {
  estrella: {
    titulo: 'Estrellas',
    color: CHART.utilidad,
    accion: 'Alto volumen y alto margen: invierte y promociona activamente.',
  },
  vaca_lechera: {
    titulo: 'Vacas lecheras',
    color: CHART.ingresos,
    accion: 'Alto volumen, margen bajo: sostienen la caja — optimiza costo de compra o logística.',
  },
  oportunidad: {
    titulo: 'Oportunidades',
    color: CHART.gastos,
    accion: 'Margen alto con poco volumen: prueba marketing o venta cruzada para subir volumen.',
  },
  problema: {
    titulo: 'Problemas',
    color: CHART.alerta,
    accion: 'Bajo volumen y bajo margen: rediseña precio, renegocia costo o evalúa descontinuar.',
  },
}

export default function ProfitabilityInsights({ metrics }: { metrics: MetricsResult }) {
  const analisis = metrics.analisis_rentabilidad
  const puntos = useMemo(() => {
    if (!analisis) return []
    return [...analisis.clasificacion_productos]
      .sort((a, b) => b.ingresos - a.ingresos)
      .slice(0, 60)
  }, [analisis])
  if (!analisis) return null
  const umbrales = analisis.umbrales
  const conteo = analisis.clasificacion_productos.reduce(
    (acc, item) => ({ ...acc, [item.cuadrante]: (acc[item.cuadrante] ?? 0) + 1 }),
    {} as Record<Producto['cuadrante'], number>,
  )
  const margenMensual = (metrics.evolucion_mensual ?? [])
    .filter((mes) => mes.margen_pareado_pct != null)
    .map((mes) => ({ mes: mes.mes, margen: mes.margen_pareado_pct as number, parcial: mes.parcial }))
  const bajoCosto = analisis.ventas_bajo_costo
  const negativos = analisis.productos_margen_negativo

  return (
    <section className="mb-7 space-y-5">
      <Card className="border-navy/15 bg-gradient-to-br from-teal/[0.04] via-white to-navy/[0.03]">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-navy/45">
          Explorar · rentabilidad para decidir
        </p>
        <h2 className="mt-1 text-base font-semibold text-navy">¿Dónde ganas y dónde pierdes plata?</h2>
        <p className="mt-1 max-w-3xl text-xs leading-relaxed text-navy/65">
          Cada producto se clasifica cruzando su participación en las ventas con su margen,
          comparado contra la mediana de TU archivo (no contra rangos abstractos). El objetivo
          no es el número: es la decisión que gatilla.
        </p>

        {umbrales && puntos.length > 0 && (
          <div className="mt-4 grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
            <div>
              <h3 className="text-sm font-semibold text-navy">Mapa del portafolio</h3>
              <p className="mt-0.5 text-xs text-navy/55">
                Participación en ventas brutas (eje horizontal) vs margen (vertical). Líneas =
                medianas de tu negocio ({formatNumber(umbrales.participacion_mediana_pct)}% y{' '}
                {formatNumber(umbrales.margen_mediano_pct)}%). Los {puntos.length} productos con más ingresos.
              </p>
              <div className="mt-3 h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
                    <XAxis
                      type="number"
                      dataKey="participacion_bruta_pct"
                      name="Participación"
                      tickFormatter={(value: number) => `${formatNumber(value)}%`}
                      tick={{ fill: AXIS_INK, fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      type="number"
                      dataKey="margen_pct"
                      name="Margen"
                      tickFormatter={(value: number) => `${formatNumber(value)}%`}
                      tick={{ fill: AXIS_INK, fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                      width={56}
                    />
                    <ZAxis type="number" dataKey="ingresos" range={[40, 240]} name="Ingresos" />
                    <ReferenceLine x={umbrales.participacion_mediana_pct} stroke={AXIS_INK} strokeDasharray="4 4" />
                    <ReferenceLine y={umbrales.margen_mediano_pct} stroke={AXIS_INK} strokeDasharray="4 4" />
                    <Tooltip
                      cursor={{ strokeDasharray: '3 3' }}
                      content={({ active, payload }) => {
                        if (!active || !payload?.length) return null
                        const punto = payload[0]?.payload as Producto | undefined
                        if (!punto) return null
                        return (
                          <div className="rounded-lg border border-navy/10 bg-white px-3 py-2 text-xs shadow-md">
                            <p className="font-semibold text-navy">{punto.nombre}</p>
                            <p className="mt-1 text-navy/70">
                              Margen {formatNumber(punto.margen_pct)}% · participación{' '}
                              {formatNumber(punto.participacion_bruta_pct)}%
                            </p>
                            <p className="text-navy/70">Ingresos {formatCLP(punto.ingresos)}</p>
                            <p className="mt-1 font-semibold" style={{ color: CUADRANTES[punto.cuadrante].color }}>
                              {CUADRANTES[punto.cuadrante].titulo}
                            </p>
                          </div>
                        )
                      }}
                    />
                    <Scatter data={puntos} isAnimationActive={false}>
                      {puntos.map((punto) => (
                        <Cell key={punto.nombre} fill={CUADRANTES[punto.cuadrante].color} fillOpacity={0.75} />
                      ))}
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="grid content-start gap-3">
              {(Object.keys(CUADRANTES) as Producto['cuadrante'][]).map((clave) => (
                <div
                  key={clave}
                  className="rounded-xl border border-navy/10 bg-white/85 p-3.5"
                  style={{ borderLeft: `4px solid ${CUADRANTES[clave].color}` }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-navy">{CUADRANTES[clave].titulo}</p>
                    <span className="rounded-full bg-navy/[0.06] px-2.5 py-0.5 text-xs font-bold text-navy">
                      {formatNumber(conteo[clave] ?? 0)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-navy/65">{CUADRANTES[clave].accion}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      {(negativos.length > 0 || bajoCosto.filas > 0 || analisis.filas_margen_atipico > 0) && (
        <div className="grid items-start gap-5 xl:grid-cols-2">
          {negativos.length > 0 && (
            <Card className="border-coral/25">
              <h3 className="text-sm font-semibold text-navy">Productos que destruyen margen</h3>
              <p className="mt-0.5 text-xs text-navy/55">
                Venden bajo su costo: cada venta adicional AUMENTA la pérdida. Revisa precio,
                costo de referencia o descontinúa.
              </p>
              <div className="mt-3 h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={negativos.slice(0, 8).map((item) => ({
                      ...item,
                      etiqueta: truncateLabel(item.nombre, 22),
                    }))}
                    layout="vertical"
                    margin={{ top: 4, right: 24, bottom: 4, left: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
                    <XAxis
                      type="number"
                      tickFormatter={formatCLPCompact}
                      tick={{ fill: AXIS_INK, fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="etiqueta"
                      width={150}
                      tick={{ fill: AXIS_INK, fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      formatter={(value, name) =>
                        name === 'Utilidad' ? formatCLP(Number(value)) : `${formatNumber(Number(value))}%`
                      }
                    />
                    <Bar dataKey="utilidad" name="Utilidad" fill={CHART.alerta} radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              {negativos.length > 8 && (
                <p className="mt-2 text-xs text-navy/50">
                  Y {formatNumber(negativos.length - 8)} producto(s) más con margen negativo.
                </p>
              )}
            </Card>
          )}
          <div className="grid content-start gap-4">
            {bajoCosto.filas > 0 && (
              <Card className="border-coral/25 bg-gradient-to-br from-coral/[0.05] to-transparent">
                <h3 className="text-sm font-semibold text-navy">Ventas bajo el costo</h3>
                <p className="mt-1 text-2xl font-bold text-coral">{formatNumber(bajoCosto.filas)}</p>
                <p className="text-xs text-navy/60">
                  venta(s) donde el ingreso no cubre el costo de la fila: en conjunto explican{' '}
                  <strong className="text-navy">{formatCLP(bajoCosto.perdida)}</strong> de pérdida bruta.
                  Si el margen global te parece imposible, la explicación suele partir aquí — valida
                  primero esos costos en Limpieza.
                </p>
              </Card>
            )}
            {analisis.filas_margen_atipico > 0 && (
              <Card className="border-gold/30 bg-gradient-to-br from-gold/[0.06] to-transparent">
                <h3 className="text-sm font-semibold text-navy">Márgenes atípicos por fila</h3>
                <p className="mt-1 text-2xl font-bold text-navy">{formatNumber(analisis.filas_margen_atipico)}</p>
                <p className="text-xs text-navy/60">
                  fila(s) con margen muy fuera del rango del negocio: suelen ser errores de precio,
                  descuentos no autorizados o costos mal cargados. Están señaladas en la descarga
                  (Observaciones) para revisarlas una a una.
                </p>
              </Card>
            )}
          </div>
        </div>
      )}

      {margenMensual.length >= 2 && (
        <Card>
          <h3 className="text-sm font-semibold text-navy">Margen bruto mes a mes</h3>
          <p className="mt-0.5 text-xs text-navy/55">
            Una caída sostenida del margen con ingresos estables = costos subiendo sin traspaso a
            precios. Solo meses con cobertura de costos; el margen usa ingreso y costo PAREADOS.
          </p>
          <div className="mt-4 h-52">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={margenMensual} margin={{ top: 6, right: 12, bottom: 0, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
                <XAxis
                  dataKey="mes"
                  tickFormatter={formatMonthShort}
                  tick={{ fill: AXIS_INK, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tickFormatter={(value: number) => `${formatNumber(value)}%`}
                  tick={{ fill: AXIS_INK, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={56}
                />
                <ReferenceLine y={0} stroke={AXIS_INK} strokeDasharray="4 4" />
                <Tooltip
                  formatter={(value) => [`${formatNumber(Number(value))}%`, 'Margen pareado']}
                  labelFormatter={(label) => formatMonthShort(String(label))}
                />
                <Line
                  type="monotone"
                  dataKey="margen"
                  name="Margen pareado"
                  stroke={CHART.utilidad}
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
    </section>
  )
}
