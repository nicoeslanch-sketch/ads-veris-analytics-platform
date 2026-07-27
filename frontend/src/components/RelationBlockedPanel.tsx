import { AlertTriangle, ArrowRight, Link2 } from 'lucide-react'
import Card from './ui/Card'
import type { RelationBlockedNotice } from '../lib/relationBlocked'

/** Reemplaza el error crudo + "Reintentar" (que no podía funcionar) por la
 * explicación de negocio y la única acción que sí resuelve el bloqueo. */
export default function RelationBlockedPanel({
  notice,
  onOpenRelations,
}: {
  notice: RelationBlockedNotice
  onOpenRelations: () => void
}) {
  return (
    <Card className="border-gold/40 bg-gold/[0.06]">
      <div className="flex flex-wrap items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gold/15 text-gold">
          <AlertTriangle className="h-4.5 w-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-navy">{notice.titulo}</h2>
          <p className="mt-1.5 text-sm leading-relaxed text-navy/70">{notice.explicacion}</p>
          <p className="mt-1.5 text-sm leading-relaxed text-navy/70">{notice.consecuencia}</p>
          <p className="mt-3 text-xs text-navy/50">
            Reintentar no cambia nada: hay que elegir otra relación o quitarla.
          </p>
          <button
            type="button"
            onClick={onOpenRelations}
            className="mt-3 inline-flex items-center gap-2 rounded-lg bg-teal px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal/90"
          >
            <Link2 className="h-4 w-4" />
            Ir a Relación manual
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </Card>
  )
}
