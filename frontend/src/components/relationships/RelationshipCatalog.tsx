import { useMemo, useState } from 'react'
import {
  Boxes,
  CircleDollarSign,
  PackageSearch,
  Plus,
  Search,
  ShieldCheck,
  ShoppingCart,
  Users,
} from 'lucide-react'
import type { CatalogRelationship, RelationshipTemplate } from '../../lib/types'
import {
  filterRelationships,
  sortRelationships,
  templateLabel,
} from '../../lib/relationshipDashboard'

const TEMPLATE_ICON: Partial<Record<RelationshipTemplate, typeof Boxes>> = {
  sales_costs: CircleDollarSign,
  products_sales: Boxes,
  sales_inventory: PackageSearch,
  sales_customers: Users,
  sales_sellers: Users,
  purchases_costs: ShoppingCart,
}

const TEMPLATE_ACCENT: Partial<Record<RelationshipTemplate, string>> = {
  sales_costs: 'text-coral',
  products_sales: 'text-green',
  sales_inventory: 'text-gold',
  sales_customers: 'text-teal',
  sales_sellers: 'text-gold',
  sales_branches: 'text-teal',
  purchases_costs: 'text-gold',
  expenses_branches: 'text-coral',
}

type CatalogFilter = 'all' | 'sales' | 'operations'

interface RelationshipCatalogProps {
  relationships: CatalogRelationship[]
  selectedId: string | null
  onSelect: (relation: CatalogRelationship) => void
  onCreate: () => void
  discardedCount?: number
}

/** Panel izquierdo: buscador + lista de conexiones seguras + crear personalizada. */
export default function RelationshipCatalog({
  relationships,
  selectedId,
  onSelect,
  onCreate,
  discardedCount = 0,
}: RelationshipCatalogProps) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<CatalogFilter>('all')
  const visible = useMemo(
    () => sortRelationships(filterRelationships(relationships, query)).filter((relation) => {
      if (filter === 'all') return true
      if (filter === 'sales') return relation.template.startsWith('sales_')
        || relation.template === 'products_sales'
      return !relation.template.startsWith('sales_')
        && relation.template !== 'products_sales'
    }),
    [relationships, query, filter],
  )

  return (
    <aside
      className="flex min-w-0 flex-col gap-3.5 overflow-hidden rounded-xl border border-navy bg-navy p-4 shadow-sm"
      aria-label="Catálogo de relaciones"
    >
      <div>
        <h3 className="text-base font-bold leading-6 text-white">Selecciona una conexión</h3>
        <p className="mt-1 text-xs leading-relaxed text-white/80">
          {relationships.filter((relation) => relation.source === 'automatic').length}{' '}
          conexión(es) segura(s) detectada(s).
        </p>
      </div>

      <label className="relative block">
        <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/45" aria-hidden />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Buscar hoja, clave o tipo"
          aria-label="Buscar conexión"
          className="w-full rounded-lg border border-white/15 bg-white/10 py-2 pl-8 pr-2.5 text-xs text-white placeholder:text-white/45 outline-none focus:border-teal"
        />
      </label>

      <div className="grid grid-cols-3 gap-1 rounded-lg bg-black/10 p-1" aria-label="Filtrar conexiones">
        {([
          ['all', 'Todas'],
          ['sales', 'Ventas'],
          ['operations', 'Otras'],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            type="button"
            aria-pressed={filter === value}
            onClick={() => setFilter(value)}
            className={`rounded-md px-1.5 py-1.5 text-[10px] font-semibold transition-colors ${
              filter === value ? 'bg-white text-navy shadow-sm' : 'text-white/65 hover:text-white'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <ul className="flex max-h-[42rem] min-w-0 flex-col gap-2.5 overflow-y-auto pr-1">
        {visible.map((relation) => {
          const active = relation.id === selectedId
          const Icon = TEMPLATE_ICON[relation.template] ?? Boxes
          const accent = TEMPLATE_ACCENT[relation.template] ?? 'text-teal'
          const coverage = Math.round(relation.coverage_left * 100)
          return (
            <li key={relation.id}>
              <button
                type="button"
                aria-pressed={active}
                onClick={() => onSelect(relation)}
                className={[
                  'w-full min-w-0 overflow-hidden rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/60',
                  active
                    ? 'border-teal bg-white shadow-md ring-1 ring-teal/30'
                    : 'border-white/10 bg-white/[0.07] hover:border-white/25 hover:bg-white/10',
                ].join(' ')}
              >
                <div className="flex min-w-0 items-start gap-2.5">
                  <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${
                    active ? 'bg-navy/[0.06]' : 'bg-white/10'
                  }`}>
                    <Icon className={`h-4 w-4 ${accent}`} aria-hidden />
                  </span>
                  <span className={`min-w-0 flex-1 break-words text-[13px] font-semibold leading-5 [overflow-wrap:anywhere] ${
                    active ? 'text-navy' : 'text-white'
                  }`}>
                    {relation.label}
                  </span>
                  {active && (
                    <span className="shrink-0 rounded-full bg-teal px-2 py-0.5 text-[10px] font-semibold text-white">
                      Activa
                    </span>
                  )}
                </div>
                <p className={`mt-1.5 break-words text-[11px] leading-4 [overflow-wrap:anywhere] ${active ? 'text-navy/70' : 'text-white/80'}`}>
                  {relation.append_sheets?.length
                    ? `${relation.append_sheets.length} hojas de ventas apiladas`
                    : `${relation.left_sheet} + ${relation.right_sheet}`}
                </p>
                <p className={`mt-1 break-words text-[11px] leading-4 [overflow-wrap:anywhere] ${active ? 'text-navy/65' : 'text-white/75'}`}>
                  {relation.left_keys.join(' + ')} ↔ {relation.right_keys.join(' + ')}
                </p>
                <div className={`mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] leading-4 ${
                  active ? 'text-navy/70' : 'text-white/75'
                }`}>
                  <span className="inline-flex items-center gap-0.5 text-green">
                    <ShieldCheck className="h-3 w-3" aria-hidden /> Segura
                  </span>
                  <span>·</span>
                  <span>{templateLabel(relation.template)}</span>
                  <span>·</span>
                  <span>{coverage}% filas</span>
                  {relation.recommended && (
                    <span className="rounded bg-gold/20 px-1 py-0.5 font-semibold text-gold">
                      Recomendada
                    </span>
                  )}
                </div>
              </button>
            </li>
          )
        })}
        {visible.length === 0 && (
          <li className="rounded-lg border border-dashed border-white/20 p-3 text-center text-[11px] text-white/55">
            Sin conexiones que coincidan con la búsqueda.
          </li>
        )}
      </ul>

      <button
        type="button"
        onClick={onCreate}
        className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-teal/70 bg-teal/10 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-teal/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/60"
      >
        <Plus className="h-3.5 w-3.5" aria-hidden /> Crear conexión personalizada
      </button>
      {discardedCount > 0 && (
        <p className="rounded-lg bg-black/10 px-3 py-2.5 text-[11px] leading-relaxed text-white/75">
          {discardedCount} cruce(s) se ocultaron porque tenían 0% de correspondencia,
          duplicaban filas o no tenían una plantilla empresarial válida.
        </p>
      )}
    </aside>
  )
}
