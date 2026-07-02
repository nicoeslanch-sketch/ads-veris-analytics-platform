import { Bell } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import EmptyState from '../components/ui/EmptyState'

export default function Alertas() {
  return (
    <>
      <PageHeader
        title="Alertas"
        subtitle="Tu sistema de aviso temprano: vigilancia automática y preventiva de tu negocio."
      />
      <EmptyState
        icon={Bell}
        title="Sin alertas por ahora"
        description="Cuando cargues datos podrás definir reglas (ej.: avisar si las ventas bajan más de 10%) y recibir alertas con severidad, área afectada y recomendación."
      />
    </>
  )
}
