import { FileText } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import EmptyState from '../components/ui/EmptyState'

export default function Reportes() {
  return (
    <>
      <PageHeader
        title="Reportes"
        subtitle="Genera y descarga reportes de tu dashboard, indicadores y análisis."
      />
      <EmptyState
        icon={FileText}
        title="No hay reportes disponibles"
        description="Cuando tu dashboard tenga datos podrás exportar reportes en PDF y Excel para compartirlos con tu equipo o tu contador."
        ctaLabel="Cargar mis datos"
        ctaTo="/estandarizacion"
      />
    </>
  )
}
