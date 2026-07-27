import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  ArrowDownRight,
  ArrowUpRight,
  BadgeDollarSign,
  CircleDollarSign,
  ChevronDown,
  ChevronRight,
  HandCoins,
  ListChecks,
  Percent,
  ReceiptText,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import Card from './ui/Card'
import KpiValue from './ui/KpiValue'
import {
  AXIS_INK,
  CATEGORICAL,
  GRID_STROKE,
  truncateLabel,
} from '../lib/charts'
import { formatNumber } from '../lib/format'
import type {
  BusinessAnalysis,
  CollectionGroupRow,
  NominalCollectionAnalysis,
} from '../lib/types'

type Variant = 'summary' | 'explore'

const COLLECTION_COLORS = ['#0f9f75', '#2378c3', '#8b5cc7', '#e59a20', '#e15c4b', '#5f7890']

function currency(value: number | null | undefined, code: string, compact = false) {
  if (value == null) return 'No disponible'
  return new Intl.NumberFormat('es-CL', {
    style: 'currency',
    currency: code,
    currencyDisplay: 'narrowSymbol',
    notation: compact ? 'compact' : 'standard',
    maximumFractionDigits: compact ? 1 : 0,
  }).format(value)
}

function variation(value: number | null) {
  if (value == null) return (
    <span className="text-[10px] text-navy/40">Sin base comparable</span>
  )
  const positive = value >= 0
  const Icon = positive ? ArrowUpRight : ArrowDownRight
  return (
    <span className={positive ? 'inline-flex items-center gap-1 text-[10px] font-semibold text-green' : 'inline-flex items-center gap-1 text-[10px] font-semibold text-coral'}>
      <Icon className="h-3 w-3" />
      {formatNumber(Math.abs(value))}% vs periodo anterior
    </span>
  )
}

function KpiCard({
  title,
  value,
  note,
  color,
  icon: Icon,
  comparison,
}: {
  title: string
  value: string
  note: string
  color: string
  icon: typeof HandCoins
  comparison?: ReactNode
}) {
  return (
    <Card
      className="!p-4"
      style={{ background: `linear-gradient(145deg, ${color}15, #fff 70%)` }}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-navy/55">{title}</p>
        <span
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full"
          style={{ backgroundColor: `${color}18`, color }}
        >
          <Icon className="h-4.5 w-4.5" />
        </span>
      </div>
      {/* Fuera de la fila del icono: así el valor se centra respecto de TODA
          la tarjeta y dispone del ancho completo para agrandarse. */}
      <KpiValue value={value} maxPx={24} className="mt-2" />
      <div className="mt-2 min-h-[16px]">{comparison}</div>
      <p className="mt-1 text-[10px] leading-relaxed text-navy/45">{note}</p>
    </Card>
  )
}

function CollectionDonut({
  title,
  subtitle,
  rows,
  code,
}: {
  title: string
  subtitle: string
  rows: CollectionGroupRow[]
  code: string
}) {
  if (!rows.length) return null
  const total = rows.reduce((sum, row) => sum + row.valor, 0)
  return (
    <Card className="min-w-0">
      <h3 className="text-sm font-semibold text-navy">{title}</h3>
      <p className="mt-1 text-[11px] text-navy/50">{subtitle}</p>
      <div className="mt-3 grid items-center gap-3 sm:grid-cols-[190px_1fr]">
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={rows} dataKey="valor" nameKey="nombre" innerRadius={48} outerRadius={78}>
                {rows.map((row, index) => (
                  <Cell key={row.nombre} fill={COLLECTION_COLORS[index % COLLECTION_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => currency(Number(value), code)} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="space-y-2">
          {rows.map((row, index) => (
            <div key={row.nombre} className="flex items-start justify-between gap-3 text-[11px]">
              <span className="flex min-w-0 items-center gap-2 text-navy/65">
                <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: COLLECTION_COLORS[index % COLLECTION_COLORS.length] }} />
                <span className="break-words">{row.nombre}</span>
              </span>
              <span className="shrink-0 text-right font-semibold text-navy">
                {formatNumber(total ? row.valor / total * 100 : 0)}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  )
}

function ExecutiveCollection({
  collection,
}: {
  collection: NominalCollectionAnalysis
}) {
  const { kpis, comparacion } = collection
  const teams = collection.equipos
    .filter((row) => row.subgrupo == null)
    .map((row) => ({
      nombre: row.equipo,
      valor: row.recaudacion_cobranza,
      participacion_pct: row.participacion_pct,
    }))
  const agencyRows = collection.agencias.map((row) => ({
    ...row,
    etiqueta: truncateLabel(row.nombre, 24),
  }))
  const comparisonRows = [
    { periodo: 'Periodo anterior', valor: comparacion.recaudacion_anterior ?? 0 },
    { periodo: 'Periodo actual', valor: comparacion.recaudacion_actual },
  ]
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        <KpiCard
          title="Recaudación de cobranza"
          value={currency(kpis.recaudacion_cobranza, collection.moneda)}
          note="Valor Nominal con Lote ≤ 300"
          color="#159568"
          icon={HandCoins}
          comparison={variation(comparacion.variacion_pct)}
        />
        <KpiCard
          title="Recaudación total"
          value={currency(kpis.recaudacion_total, collection.moneda)}
          note="Todos los lotes visibles"
          color="#2378c3"
          icon={CircleDollarSign}
        />
        <KpiCard
          title="Diferencia"
          value={currency(kpis.diferencia, collection.moneda)}
          note="Total menos cobranza"
          color="#e59a20"
          icon={BadgeDollarSign}
        />
        <KpiCard
          title="% diferencia"
          value={kpis.diferencia_pct == null ? 'No disponible' : `${formatNumber(kpis.diferencia_pct)}%`}
          note={`${formatNumber(kpis.participacion_cobranza_pct ?? 0)}% corresponde a cobranza`}
          color="#8b5cc7"
          icon={Percent}
        />
        <KpiCard
          title="Pagos registrados"
          value={formatNumber(kpis.registros)}
          note={`${formatNumber(kpis.pagos_positivos)} tienen valor positivo; no existe ID único`}
          color="#13939a"
          icon={ListChecks}
        />
        <KpiCard
          title="Ticket promedio cobranza"
          value={currency(kpis.ticket_promedio_cobranza, collection.moneda)}
          note={`Sobre ${formatNumber(kpis.registros_cobranza)} registros con Lote ≤ 300`}
          color="#315eb4"
          icon={ReceiptText}
        />
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-3">
        <Card className="min-w-0 xl:col-span-2">
          <h3 className="text-sm font-semibold text-navy">Recaudación de cobranza vs recaudación total</h3>
          <p className="mt-1 text-[11px] text-navy/50">
            Serie por {collection.grano_temporal}; ambos valores reaccionan a los mismos filtros.
          </p>
          <div className="mt-3 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={collection.evolucion} margin={{ top: 8, right: 18, bottom: 8, left: 4 }}>
                <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                <XAxis dataKey="periodo" tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={28} />
                <YAxis tickFormatter={(value) => currency(Number(value), collection.moneda, true)} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} width={74} />
                <Tooltip formatter={(value) => currency(Number(value), collection.moneda)} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="recaudacion_cobranza" name="Cobranza (Lote ≤ 300)" stroke="#159568" strokeWidth={2.5} dot={{ r: 2.5 }} />
                <Line type="monotone" dataKey="recaudacion_total" name="Total" stroke="#2378c3" strokeWidth={2.5} dot={{ r: 2.5 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <CollectionDonut
          title="Participación en cobranza por equipo"
          subtitle="Solo Valor Nominal de registros con Lote ≤ 300."
          rows={teams}
          code={collection.moneda}
        />
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-2">
        <Card className="min-w-0">
          <h3 className="text-sm font-semibold text-navy">Recaudación por agencia de pago</h3>
          <p className="mt-1 text-[11px] text-navy/50">Top 10 agencias; el resto se agrupa como Otros.</p>
          <div style={{ height: Math.max(260, agencyRows.length * 32 + 60) }} className="mt-3">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={agencyRows} layout="vertical" margin={{ top: 4, right: 18, bottom: 4, left: 10 }}>
                <CartesianGrid stroke={GRID_STROKE} horizontal={false} />
                <XAxis type="number" tickFormatter={(value) => currency(Number(value), collection.moneda, true)} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="etiqueta" width={150} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip formatter={(value) => currency(Number(value), collection.moneda)} />
                <Bar dataKey="valor" name="Recaudación cobranza" radius={[0, 4, 4, 0]}>
                  {agencyRows.map((row, index) => (
                    <Cell key={row.nombre} fill={CATEGORICAL[index % CATEGORICAL.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card className="min-w-0">
          <h3 className="text-sm font-semibold text-navy">Periodo actual vs periodo anterior</h3>
          <p className="mt-1 text-[11px] text-navy/50">
            Misma cantidad de días. Si el periodo anterior es cero, no se fabrica un 100%.
          </p>
          <div className="mt-3 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={comparisonRows} margin={{ top: 14, right: 18, bottom: 8, left: 4 }}>
                <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                <XAxis dataKey="periodo" tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={(value) => currency(Number(value), collection.moneda, true)} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} width={74} />
                <Tooltip formatter={(value) => currency(Number(value), collection.moneda)} />
                <Bar dataKey="valor" name="Recaudación de cobranza" radius={[5, 5, 0, 0]}>
                  <Cell fill="#8ab7df" />
                  <Cell fill="#159568" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {!comparacion.base_comparable && (
            <p className="rounded-lg bg-gold/10 px-3 py-2 text-[11px] text-navy/65">
              Sin base comparable: el periodo anterior no contiene recaudación.
            </p>
          )}
        </Card>
      </div>
    </div>
  )
}

function CollectionDetail({
  collection,
}: {
  collection: NominalCollectionAnalysis
}) {
  const [judicialOpen, setJudicialOpen] = useState(true)
  const teamRows = collection.equipos.filter(
    (row) => row.subgrupo == null || judicialOpen,
  )
  return (
    <div className="space-y-4">
      <div className="grid items-start gap-4 xl:grid-cols-2">
        <Card className="min-w-0 overflow-hidden">
          <h3 className="text-sm font-semibold text-navy">Recaudación por equipo y subgrupo</h3>
          <p className="mt-1 text-[11px] text-navy/50">
            Judicial se abre en sus estudios; la participación general siempre usa la cobranza visible.
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-[720px] w-full text-left text-[11px]">
              <thead className="bg-navy/[0.04] text-navy/55">
                <tr>
                  <th className="px-3 py-2 font-semibold">Equipo / subgrupo</th>
                  <th className="px-3 py-2 text-right font-semibold">Cobranza</th>
                  <th className="px-3 py-2 text-right font-semibold">Total</th>
                  <th className="px-3 py-2 text-right font-semibold">Diferencia</th>
                  <th className="px-3 py-2 text-right font-semibold">Participación</th>
                </tr>
              </thead>
              <tbody>
                {teamRows.map((row) => (
                  <tr key={`${row.equipo}-${row.subgrupo ?? 'total'}`} className="border-b border-navy/7 last:border-0">
                    <td className={row.subgrupo ? 'px-3 py-2 pl-8 text-navy/60' : 'px-3 py-2 font-semibold text-navy'}>
                      {row.subgrupo ? row.subgrupo : row.equipo === 'JUDICIAL' ? (
                        <button
                          type="button"
                          aria-expanded={judicialOpen}
                          onClick={() => setJudicialOpen((open) => !open)}
                          className="inline-flex items-center gap-1.5 text-left font-semibold text-navy hover:text-teal"
                        >
                          {judicialOpen
                            ? <ChevronDown className="h-3.5 w-3.5" />
                            : <ChevronRight className="h-3.5 w-3.5" />}
                          JUDICIAL (total)
                        </button>
                      ) : row.equipo}
                    </td>
                    <td className="px-3 py-2 text-right font-medium text-navy">{currency(row.recaudacion_cobranza, collection.moneda)}</td>
                    <td className="px-3 py-2 text-right text-navy/65">{currency(row.recaudacion_total, collection.moneda)}</td>
                    <td className="px-3 py-2 text-right text-navy/65">{currency(row.diferencia, collection.moneda)}</td>
                    <td className="px-3 py-2 text-right text-navy/65">
                      {formatNumber(row.subgrupo ? row.participacion_equipo_pct ?? 0 : row.participacion_pct ?? 0)}%
                      {row.subgrupo && <span className="ml-1 text-[9px] text-navy/35">del equipo</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <CollectionDonut
          title="Recaudación por forma de pago"
          subtitle="Cinco o seis categorías principales y el resto agrupado como Otros."
          rows={collection.formas_pago}
          code={collection.moneda}
        />
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-2">
        <Card className="min-w-0">
          <h3 className="text-sm font-semibold text-navy">Recaudación por periodo cotizado</h3>
          <p className="mt-1 text-[11px] text-navy/50">Últimos 12 periodos, ordenados cronológicamente; no se confunden con Fecha Pago.</p>
          <div className="mt-3 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={collection.periodos_cotizados} margin={{ top: 8, right: 12, bottom: 8, left: 4 }}>
                <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                <XAxis dataKey="periodo" tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={(value) => currency(Number(value), collection.moneda, true)} tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} width={74} />
                <Tooltip formatter={(value) => currency(Number(value), collection.moneda)} />
                <Bar dataKey="valor" name="Recaudación cobranza" fill="#13939a" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card className="min-w-0">
          <h3 className="text-sm font-semibold text-navy">Descripción del pago</h3>
          <p className="mt-1 text-[11px] text-navy/50">La fuente es Descripción Lote; no se inventa una columna inexistente.</p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[480px] text-left text-[11px]">
              <thead className="bg-navy/[0.04] text-navy/55">
                <tr>
                  <th className="px-3 py-2 font-semibold">Descripción</th>
                  <th className="px-3 py-2 text-right font-semibold">Recaudación</th>
                  <th className="px-3 py-2 text-right font-semibold">% participación</th>
                </tr>
              </thead>
              <tbody>
                {collection.descripciones_pago.map((row) => (
                  <tr key={row.nombre} className="border-b border-navy/7 last:border-0">
                    <td className="px-3 py-2 text-navy/70">{row.nombre}</td>
                    <td className="px-3 py-2 text-right font-semibold text-navy">{currency(row.valor, collection.moneda)}</td>
                    <td className="px-3 py-2 text-right text-navy/60">{formatNumber(row.participacion_pct ?? 0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  )
}

export default function NominalCollectionDashboard({
  analysis,
  variant,
}: {
  analysis: BusinessAnalysis
  variant: Variant
}) {
  const collection = analysis.cobranza
  if (!collection) return null
  return (
    <section className="space-y-4" aria-label="Dashboard adaptativo de cobranza">
      <Card className="border-teal/20 bg-gradient-to-r from-teal/[0.06] via-white to-blue-50/40">
        <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-teal">Perfil detectado</p>
        <h2 className="mt-1 text-lg font-semibold text-navy">Cobranza basada en Valor Nominal</h2>
        <p className="mt-1 max-w-4xl text-xs leading-relaxed text-navy/55">
          ADS Veris reconoció Valor Nominal, Lote y Fecha Pago. Todas las visualizaciones parten de esa medida;
          la recaudación de cobranza añade únicamente la condición Lote ≤ 300 después de aplicar los filtros.
        </p>
      </Card>
      {variant === 'summary'
        ? <ExecutiveCollection collection={collection} />
        : <CollectionDetail collection={collection} />}
    </section>
  )
}
