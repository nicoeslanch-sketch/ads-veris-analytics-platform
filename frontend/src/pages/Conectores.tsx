import { Plug } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import EmptyState from '../components/ui/EmptyState'

export default function Conectores() {
  return (
    <>
      <PageHeader
        title="Conectores"
        subtitle="Conecta tus fuentes de datos: archivos Excel/CSV primero; Google Sheets y bases SQL más adelante."
      />
      <EmptyState
        icon={Plug}
        title="Sin fuentes conectadas"
        description="En el MVP podrás cargar archivos Excel y CSV. Las integraciones con Google Sheets, SQL y otras fuentes llegan en fases posteriores."
        ctaLabel="Cargar un archivo"
        ctaTo="/estandarizacion"
      />
    </>
  )
}
