import Card from './ui/Card'
import { formatCLP, formatNumber } from '../lib/format'
import type { MetricsResult } from '../lib/types'

export default function AdaptiveProfileSummary({ metrics }: { metrics: MetricsResult }) {
  const campaign = metrics.analisis_campanas
  const inventory = metrics.analisis_inventario
  const generic = metrics.analisis_generico
  if (campaign) {
    const cards = [
      ['Campañas', formatNumber(campaign.campanas)],
      ['Inversión', formatCLP(campaign.inversion)],
      ['Impresiones', formatNumber(campaign.impresiones)],
      ['Clics', formatNumber(campaign.clics)],
      ['CTR', campaign.ctr_pct == null ? '—' : `${formatNumber(campaign.ctr_pct)}%`],
      ['CPC', campaign.cpc == null ? '—' : formatCLP(campaign.cpc)],
    ]
    return <Profile title="Rendimiento de campañas" cards={cards} groups={[['Plataformas', campaign.plataformas], ['Estados', campaign.estados]]} />
  }
  if (inventory) {
    const cards = [
      ['Registros', formatNumber(inventory.registros)],
      ['Productos', formatNumber(inventory.productos)],
      ['Stock total', formatNumber(inventory.stock_total)],
      ['Stock mínimo', formatNumber(inventory.stock_minimo_total)],
      ['Bajo mínimo', formatNumber(inventory.bajo_minimo)],
      ['Cobertura', `${formatNumber(inventory.cobertura_stock_pct)}%`],
    ]
    return <Profile title="Estado del inventario" cards={cards} groups={[['Sucursales', inventory.sucursales]]} />
  }
  if (!generic) return null
  return (
    <div className="space-y-5">
      <Profile title="Perfil estructural" cards={[
        ['Registros', formatNumber(generic.registros)],
        ['Columnas', formatNumber(generic.columnas)],
        ['Celdas informadas', `${formatNumber(generic.celdas_informadas_pct)}%`],
      ]} groups={[]} />
      <Card>
        <h2 className="text-sm font-semibold text-navy">Columnas disponibles</h2>
        <p className="mt-2 text-xs leading-6 text-navy/65">{generic.columnas_disponibles.join(' · ')}</p>
      </Card>
    </div>
  )
}

function Profile({ title, cards, groups }: {
  title: string
  cards: string[][]
  groups: Array<[string, Array<{ nombre: string; registros: number }>]>
}) {
  return (
    <div className="space-y-5">
      <h2 className="text-base font-semibold text-navy">{title}</h2>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map(([label, value]) => <Card key={label} className="!p-4"><p className="text-xs text-navy/50">{label}</p><p className="mt-1 text-lg font-bold text-navy">{value}</p></Card>)}
      </div>
      {groups.length > 0 && <div className="grid gap-4 lg:grid-cols-2">{groups.map(([label, rows]) => (
        <Card key={label}><h3 className="text-sm font-semibold text-navy">{label}</h3><div className="mt-3 space-y-2">{rows.map((row) => <div key={row.nombre} className="flex justify-between text-xs"><span>{row.nombre}</span><strong>{formatNumber(row.registros)}</strong></div>)}</div></Card>
      ))}</div>}
    </div>
  )
}
