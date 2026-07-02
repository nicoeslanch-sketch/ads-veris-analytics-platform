import { Search } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import EmptyState from '../components/ui/EmptyState'

export default function Explorar() {
  return (
    <>
      <PageHeader
        title="Explorar datos"
        subtitle="Encuentra respuestas, descubre patrones y entiende qué está pasando en tu negocio."
      />
      <EmptyState
        icon={Search}
        title="No hay datos que explorar todavía"
        description="Cuando tengas un dataset limpio podrás hacer análisis guiados, ver hallazgos principales y recibir recomendaciones inteligentes."
        ctaLabel="Cargar mis datos"
        ctaTo="/estandarizacion"
      />
    </>
  )
}
