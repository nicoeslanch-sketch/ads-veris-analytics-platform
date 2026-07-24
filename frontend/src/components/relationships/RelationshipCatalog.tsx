import { useMemo, useState } from 'react'
import { Boxes, Plus, Search, ShieldCheck, Users } from 'lucide-react'
import type { CatalogRelationship, RelationshipTemplate } from '../../lib/types'
import {
  filterRelationships,
  sortRelationships,
  templateLabel,
} from '../../lib/relationshipDashboard'

const TEMPLATE_ICON: Partial<Record<RelationshipTemplate, typeof Boxes>> = {
  sales_customers: Users,
  sales_sellers: Users,
}

interface RelationshipCatalogProps {
  relationships: CatalogRelationship[]
  selectedId: string | null
  onSelect: (relation: CatalogRelationship) => void
  onCreate: () => void
}

/** Panel izquierdo: buscador + lista de conexiones seguras + crear personalizada. */
export default function RelationshipCatalog({
  relationships,
  selectedId,
  onSelect,
  onCreate,
}: RelationshipCatalogProps) {
  const [query, setQuery] = useState('')
  const visible = useMemo(
    () => sortRelationships(filterRelationships(relationships, query)),
    [relationships, query],
  )

  return (
    <aside className="flex flex-col gap-3" aria-label="Catálogo de relaciones">
      <div>
        <h3 className="text-sm font-semibold text-navy">Selecciona una conexión</h3>
        <p className="mt-0.5 text-[11px] text-navy/55">
          {relationships.length} conexión(es) segura(s) detectada(s).
        </p>
      </div>

      <label className="relative block">
        <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-navy/40" aria-hidden />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Buscar hoja, clave o tipo"
          aria-label="Buscar conexión"
          className="w-full rounded-lg border border-navy/15 bg-white py-2 pl-8 pr-2.5 text-xs text-navy outline-none focus:border-teal"
        />
      </label>

      <ul className="flex max-h-[26rem] flex-col gap-2 overflow-y-auto pr-1">
        {visible.map((relation) => {
          const active = relation.id === selectedId
          const Icon = TEMPLATE_ICON[relation.template] ?? Boxes
          return (
            <li key={relation.id}>
              <button
                type="button"
                aria-pressed={active}
                onClick={() => onSelect(relation)}
                className={[
                  'w-full rounded-lg border p-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/60',
                  active
                    ? 'border-teal bg-teal/[0.07] shadow-sm'
                    : 'border-navy/10 bg-white hover:bg-navy/[0.03]',
                ].join(' ')}
              >
                <div className="flex items-center gap-2">
                  <Icon className={`h-4 w-4 shrink-0 ${active ? 'text-teal' : 'text-navy/45'}`} aria-hidden />
                  <span className="min-w-0 flex-1 truncate text-xs font-semibold text-navy">
                    {relation.label}
                  </span>
                  {active && (
                    <span className="rounded-full bg-teal px-1.5 py-0.5 text-[10px] font-semibold text-white">
                      Activa
                    </span>
                  )}
                </div>
                <p className="mt-1 truncate text-[11px] text-navy/55">
                  {relation.left_keys.join(' + ')} ↔ {relation.right_keys.join(' + ')}
                </p>
                <div className="mt-1 flex items-center gap-2 text-[10px] text-navy/50">
                  <span className="inline-flex items-center gap-0.5 text-green">
                    <ShieldCheck className="h-3 w-3" aria-hidden /> Segura
                  </span>
                  <span>·</span>
                  <span>{templateLabel(relation.template)}</span>
                  <span>·</span>
                  <span>{Math.round(relation.overlap * 100)}% cruce</span>
                </div>
              </button>
            </li>
          )
        })}
        {visible.length === 0 && (
          <li className="rounded-lg border border-dashed border-navy/15 p-3 text-center text-[11px] text-navy/50">
            Sin conexiones que coincidan con la búsqueda.
          </li>
        )}
      </ul>

      <button
        type="button"
        onClick={onCreate}
        className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-teal/40 px-3 py-2 text-xs font-semibold text-teal transition-colors hover:bg-teal/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/60"
      >
        <Plus className="h-3.5 w-3.5" aria-hidden /> Crear conexión personalizada
      </button>
    </aside>
  )
}
