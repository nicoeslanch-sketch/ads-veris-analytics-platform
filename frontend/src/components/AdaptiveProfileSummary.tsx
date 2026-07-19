import Card from './ui/Card'
import { formatCLP, formatNumber } from '../lib/format'
import { AXIS_INK, CHART, GRID_STROKE, formatCLPCompact, truncateLabel } from '../lib/charts'
import type { MetricsResult } from '../lib/types'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

/** Fase 18: los resúmenes adaptativos dejan de ser solo tarjetas — cada perfil
 * (campañas, inventario, clientes, sucursales, trabajadores, metas…) muestra
 * sus distribuciones con gráficos, siempre a partir de columnas reales. */

const GENERIC_TITLES: Record<string, { titulo: string; nota: string }> = {
  clientes: {
    titulo: 'Perfil de clientes',
    nota: 'Esta hoja se interpreta como una maestra de clientes: se resumen sus distribuciones sin inventar ventas.',
  },
  sucursales: {
    titulo: 'Red de sucursales',
    nota: 'Esta hoja se interpreta como una maestra de sucursales: se resumen sus distribuciones sin inventar ventas.',
  },
  trabajadores: {
    titulo: 'Equipo de trabajo',
    nota: 'Esta hoja se interpreta como una nómina o listado de trabajadores: se resumen cargos y montos sin tratarlos como ventas.',
  },
  metas: {
    titulo: 'Metas y objetivos',
    nota: 'Esta hoja se interpreta como metas u objetivos: se resumen sus valores sin tratarlos como ventas reales.',
  },
}

export default function AdaptiveProfileSummary({ metrics }: { metrics: MetricsResult }) {
  const campaign = metrics.analisis_campanas
  const inventory = metrics.analisis_inventario
  const generic = metrics.analisis_generico
  if (campaign) {
    const cards: string[][] = [
      ['Campañas', formatNumber(campaign.campanas)],
      ['Inversión', campaign.inversion == null ? '—' : formatCLP(campaign.inversion)],
      ['Impresiones', formatNumber(campaign.impresiones)],
      ['Clics', formatNumber(campaign.clics)],
      ['CTR', campaign.ctr_pct == null ? '—' : `${formatNumber(campaign.ctr_pct)}%`],
      ['CPC', campaign.cpc == null ? '—' : formatCLP(campaign.cpc)],
    ]
    const platforms = (campaign.por_plataforma ?? []).map((item) => ({
      ...item,
      etiqueta: truncateLabel(item.nombre, 18),
    }))
    return (
      <div className="space-y-5">
        <h2 className="text-base font-semibold text-navy">Rendimiento de campañas</h2>
        <CardGrid cards={cards} />
        {(campaign.clics_sobre_impresiones ?? 0) > 0 && (
          <p className="rounded-xl border border-gold/30 bg-gold/[0.07] px-4 py-3 text-xs leading-relaxed text-navy/70">
            {formatNumber(campaign.clics_sobre_impresiones ?? 0)} campaña(s) registran más clics
            que impresiones (CTR sobre 100%). Revísalas en el origen: suelen ser errores de
            captura o columnas intercambiadas.
          </p>
        )}
        {platforms.length > 1 && (
          <div className="grid gap-5 xl:grid-cols-2">
            <Card>
              <h3 className="text-sm font-semibold text-navy">Inversión por plataforma</h3>
              <div className="mt-4 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={platforms} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
                    <XAxis type="number" tickFormatter={formatCLPCompact} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="etiqueta" width={110} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip formatter={(value) => formatCLP(Number(value))} />
                    <Bar dataKey="inversion" name="Inversión" fill={CHART.ingresos} radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card>
              <h3 className="text-sm font-semibold text-navy">Clics y CTR por plataforma</h3>
              <div className="mt-4 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={platforms} margin={{ top: 4, right: 12, bottom: 4, left: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
                    <XAxis dataKey="etiqueta" tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tickFormatter={(value: number) => formatNumber(value)} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip
                      formatter={(value, name) =>
                        name === 'CTR %' ? `${formatNumber(Number(value))}%` : formatNumber(Number(value))
                      }
                    />
                    <Legend />
                    <Bar dataKey="clics" name="Clics" fill={CHART.flujo} radius={[3, 3, 0, 0]} />
                    <Bar dataKey="ctr_pct" name="CTR %" fill={CHART.utilidad} radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>
        )}
        <div className="grid gap-4 lg:grid-cols-2">
          <CountList title="Plataformas" rows={campaign.plataformas} />
          <CountList title="Estados" rows={campaign.estados} />
        </div>
      </div>
    )
  }
  if (inventory) {
    const cards: string[][] = [
      ['Registros', formatNumber(inventory.registros)],
      ['Productos', formatNumber(inventory.productos)],
      ['Stock total', formatNumber(inventory.stock_total)],
      ['Stock mínimo', formatNumber(inventory.stock_minimo_total)],
      ['Bajo mínimo', formatNumber(inventory.bajo_minimo)],
      ['Cobertura', `${formatNumber(inventory.cobertura_stock_pct)}%`],
    ]
    const branches = (inventory.por_sucursal ?? []).slice(0, 15).map((item) => ({
      ...item,
      etiqueta: truncateLabel(item.nombre, 16),
    }))
    return (
      <div className="space-y-5">
        <h2 className="text-base font-semibold text-navy">Estado del inventario</h2>
        <CardGrid cards={cards} />
        {(inventory.stocks_negativos ?? 0) > 0 && (
          <p className="rounded-xl border border-gold/30 bg-gold/[0.07] px-4 py-3 text-xs leading-relaxed text-navy/70">
            {formatNumber(inventory.stocks_negativos ?? 0)} registro(s) tienen stock negativo:
            pueden ser ajustes pendientes o errores de captura. Revísalos antes de valorizar
            existencias.
          </p>
        )}
        {branches.length > 1 && (
          <div className="grid gap-5 xl:grid-cols-2">
            <Card>
              <h3 className="text-sm font-semibold text-navy">Stock por sucursal</h3>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={branches} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
                    <XAxis type="number" tickFormatter={(value: number) => formatNumber(value)} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="etiqueta" width={100} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip formatter={(value) => formatNumber(Number(value))} />
                    <Bar dataKey="stock" name="Stock" fill={CHART.ingresos} radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card>
              <h3 className="text-sm font-semibold text-navy">Quiebres por sucursal</h3>
              <p className="mt-1 text-xs text-navy/55">Registros bajo el stock mínimo.</p>
              <div className="mt-4 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={branches} margin={{ top: 4, right: 12, bottom: 4, left: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
                    <XAxis dataKey="etiqueta" tick={{ fill: AXIS_INK, fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip formatter={(value) => formatNumber(Number(value))} />
                    <Bar dataKey="bajo_minimo" name="Bajo mínimo" fill={CHART.alerta} radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>
        )}
        <div className="grid gap-4 lg:grid-cols-2">
          <CountList title="Sucursales" rows={inventory.sucursales} />
        </div>
      </div>
    )
  }
  if (!generic) return null
  const meta = generic.subtipo ? GENERIC_TITLES[generic.subtipo] : null
  const distribuciones = generic.distribuciones ?? []
  const numericas = generic.numericas ?? []
  return (
    <div className="space-y-5">
      <h2 className="text-base font-semibold text-navy">{meta?.titulo ?? 'Perfil estructural'}</h2>
      {meta && (
        <p className="rounded-xl border border-teal/20 bg-teal/5 px-4 py-3 text-xs leading-relaxed text-navy/65">
          {meta.nota}
        </p>
      )}
      <CardGrid
        cards={[
          ['Registros', formatNumber(generic.registros)],
          ['Columnas', formatNumber(generic.columnas)],
          ['Celdas informadas', `${formatNumber(generic.celdas_informadas_pct)}%`],
        ]}
      />
      {numericas.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {numericas.map((item) => (
            <Card key={item.columna} className="!p-4">
              <p className="truncate text-xs text-navy/50" title={item.columna}>{item.columna}</p>
              <p className="mt-1 text-lg font-bold text-navy">{formatNumber(item.total)}</p>
              <p className="mt-1 text-[11px] text-navy/55">
                promedio {formatNumber(item.promedio)} · rango {formatNumber(item.minimo)} – {formatNumber(item.maximo)}
              </p>
            </Card>
          ))}
        </div>
      )}
      {distribuciones.length > 0 && (
        <div className="grid gap-5 xl:grid-cols-2">
          {distribuciones.map((distro) => {
            const rows = distro.valores.map((valor) => ({
              ...valor,
              etiqueta: truncateLabel(valor.nombre, 18),
            }))
            return (
              <Card key={distro.columna}>
                <h3 className="text-sm font-semibold text-navy">{distro.columna}</h3>
                <p className="mt-1 text-xs text-navy/55">
                  Registros por valor{distro.valores_totales > rows.length ? ` (top ${rows.length} de ${distro.valores_totales})` : ''}.
                </p>
                <div className="mt-4" style={{ height: Math.max(rows.length * 28 + 40, 120) }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} horizontal={false} />
                      <XAxis type="number" allowDecimals={false} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis type="category" dataKey="etiqueta" width={120} tick={{ fill: AXIS_INK, fontSize: 11 }} axisLine={false} tickLine={false} />
                      <Tooltip formatter={(value) => formatNumber(Number(value))} />
                      <Bar dataKey="registros" name="Registros" fill={CHART.ingresos} radius={[0, 3, 3, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            )
          })}
        </div>
      )}
      <Card>
        <h3 className="text-sm font-semibold text-navy">Columnas disponibles</h3>
        <p className="mt-2 text-xs leading-6 text-navy/65">{generic.columnas_disponibles.join(' · ')}</p>
      </Card>
    </div>
  )
}

function CardGrid({ cards }: { cards: string[][] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {cards.map(([label, value]) => (
        <Card key={label} className="!p-4">
          <p className="text-xs text-navy/50">{label}</p>
          <p className="mt-1 text-lg font-bold text-navy">{value}</p>
        </Card>
      ))}
    </div>
  )
}

function CountList({ title, rows }: { title: string; rows: Array<{ nombre: string; registros: number }> }) {
  if (!rows.length) return null
  return (
    <Card>
      <h3 className="text-sm font-semibold text-navy">{title}</h3>
      <div className="mt-3 space-y-2">
        {rows.map((row) => (
          <div key={row.nombre} className="flex justify-between text-xs">
            <span>{row.nombre}</span>
            <strong>{formatNumber(row.registros)}</strong>
          </div>
        ))}
      </div>
    </Card>
  )
}
