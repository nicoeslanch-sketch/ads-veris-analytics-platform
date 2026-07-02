import { LayoutDashboard } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import EmptyState from '../components/ui/EmptyState'
import { useAuth } from '../auth/AuthContext'

export default function Resumen() {
  const { user } = useAuth()
  const firstName =
    ((user?.user_metadata?.full_name as string | undefined) ?? '')
      .trim()
      .split(' ')[0] || null

  return (
    <>
      <PageHeader
        title={firstName ? `Bienvenido, ${firstName} 👋` : 'Bienvenido 👋'}
        subtitle="Este es el resumen general de tu negocio."
      />
      <EmptyState
        icon={LayoutDashboard}
        title="Aún no hay datos para mostrar"
        description="Tu dashboard con KPIs, indicadores y ratios aparecerá aquí cuando cargues y limpies tu primer archivo de datos. Todo parte de los datos."
        ctaLabel="Cargar mis datos"
        ctaTo="/estandarizacion"
      />
    </>
  )
}
