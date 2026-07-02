import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import { useAuth } from '../auth/AuthContext'

/**
 * Configuración — Fase 0: solo lectura de perfil básico.
 * La edición de perfil y preferencias de datos (moneda, fechas, redondeo)
 * se implementa junto con el pipeline (Fase 1+).
 */
export default function Configuracion() {
  const { user } = useAuth()
  const meta = (user?.user_metadata ?? {}) as Record<string, string | undefined>

  const rows: Array<{ label: string; value: string }> = [
    { label: 'Nombre', value: meta.full_name ?? '—' },
    { label: 'Correo', value: user?.email ?? '—' },
    { label: 'Empresa', value: meta.company ?? '—' },
    { label: 'Zona horaria', value: 'America/Santiago' },
    { label: 'Moneda', value: 'CLP ($)' },
    { label: 'Formato de fecha', value: 'DD/MM/YYYY' },
  ]

  return (
    <>
      <PageHeader
        title="Configuración"
        subtitle="Tu perfil, tu empresa y las preferencias de datos de la plataforma."
      />
      <div className="grid max-w-3xl gap-6">
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-navy">Perfil y cuenta</h2>
            <Badge tone="teal">Plan Básico</Badge>
          </div>
          <dl className="divide-y divide-navy/5">
            {rows.map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between py-3">
                <dt className="text-sm text-navy/60">{label}</dt>
                <dd className="text-sm font-medium text-navy">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-xs text-navy/40">
            La edición de perfil y las preferencias de datos se habilitan en las
            próximas fases.
          </p>
        </Card>
      </div>
    </>
  )
}
