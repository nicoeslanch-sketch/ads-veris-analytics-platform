import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { UploadCloud } from 'lucide-react'
import { Link } from 'react-router-dom'
import Card from './Card'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: string
  /** CTA opcional hacia el flujo de carga de datos. */
  ctaLabel?: string
  ctaTo?: string
  ctaState?: unknown
  /** Acciones extra bajo el CTA (Fase 14: demo ficticia / prueba gratuita). */
  children?: ReactNode
}

/**
 * Estado vacío estándar de los módulos (SPEC §1, regla no negociable):
 * sin datos cargados y limpios no se muestra contenido.
 */
export default function EmptyState({
  icon: Icon,
  title,
  description,
  ctaLabel,
  ctaTo,
  ctaState,
  children,
}: EmptyStateProps) {
  return (
    <Card className="flex flex-col items-center gap-4 py-16 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-teal/10">
        <Icon className="h-8 w-8 text-teal" />
      </div>
      <div>
        <h2 className="text-lg font-semibold text-navy">{title}</h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-navy/60">{description}</p>
      </div>
      {ctaLabel && ctaTo && (
        <Link
          to={ctaTo}
          state={ctaState}
          className="mt-2 inline-flex items-center gap-2 rounded-lg bg-teal px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal/90"
        >
          <UploadCloud className="h-4 w-4" />
          {ctaLabel}
        </Link>
      )}
      {children}
    </Card>
  )
}
