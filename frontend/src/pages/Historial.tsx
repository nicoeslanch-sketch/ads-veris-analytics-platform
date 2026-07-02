import { History } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import EmptyState from '../components/ui/EmptyState'

export default function Historial() {
  return (
    <>
      <PageHeader
        title="Historial"
        subtitle="Revisa todo lo que has hecho en la plataforma: cargas, limpieza, estandarización, análisis y recomendaciones."
      />
      <EmptyState
        icon={History}
        title="Todavía no hay actividad"
        description="Cada carga, limpieza, análisis y consulta al asistente quedará registrada aquí, con su detalle de antes y después."
      />
    </>
  )
}
