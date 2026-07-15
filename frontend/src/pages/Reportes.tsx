/**
 * Reportes (SPEC §7 — Fase 5, MVP).
 *
 * Exporta el estado del negocio del dataset de la sesión:
 * - Reporte ejecutivo en PDF (vista imprimible con marca → "Guardar como PDF").
 * - Datos completos en Excel/CSV (separador ';' + BOM, listo para Excel es-CL).
 */

import { useEffect, useState } from 'react'
import { FileSpreadsheet, FileText, Loader2, Lock, Printer } from 'lucide-react'
import { Link } from 'react-router-dom'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import { useAuth } from '../auth/AuthContext'
import { useSessionMetrics } from '../data/useSessionMetrics'
import { downloadReportCsv, openPrintableReport } from '../lib/report'
import { formatCLP } from '../lib/format'
import { fetchProfile } from '../lib/profile'
import { useCapability } from '../lib/usePlan'

export default function Reportes() {
  const { user } = useAuth()
  const { ready, metrics, loading, error } = useSessionMetrics()
  // Fase 7: descarga de reportes gated por plan (con enforcement apagado, libre)
  const reportsCap = useCapability('download_reports')
  const reportsLocked = reportsCap.enforced && !reportsCap.hasByPlan
  const [profileCompany, setProfileCompany] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchProfile().then((profile) => {
      if (!cancelled) setProfileCompany(profile?.company ?? null)
    })
    return () => {
      cancelled = true
    }
  }, [user?.id])

  if (!ready) {
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

  if (loading) {
    return (
      <>
        <PageHeader title="Reportes" subtitle="Preparando los datos del reporte…" />
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-teal" />
        </div>
      </>
    )
  }

  const empresa =
    profileCompany ??
    ((user?.user_metadata ?? {}) as Record<string, string | undefined>).company ??
    null

  return (
    <>
      <PageHeader
        title="Reportes"
        subtitle="Genera y descarga reportes de tu dashboard, indicadores y análisis."
      />

      {error && (
        <Card className="mb-6 border-coral/40 bg-coral/5">
          <p className="text-sm text-coral">{error}</p>
        </Card>
      )}

      {metrics && (
        <>
          <Card className="mb-6 min-w-0">
            <h2 className="text-base font-semibold text-navy">Contenido del reporte</h2>
            <p className="mt-0.5 min-w-0 text-sm text-navy/60">
              Archivo <span className="font-medium text-navy [overflow-wrap:anywhere] sm:[overflow-wrap:normal]">{metrics.archivo}</span> · periodo{' '}
              {metrics.periodo.desde ?? 'inicio'} — {metrics.periodo.hasta ?? 'fin'} · ingresos
              del periodo <span className="font-medium text-navy">{formatCLP(metrics.kpis.ingresos_totales.valor)}</span>.
              Incluye indicadores, evolución mensual, análisis por categoría, canales, top
              productos y proyección.
            </p>
          </Card>

          <div className="grid gap-6 md:grid-cols-2 xl:max-w-4xl">
            {/* PDF */}
            <Card className="flex flex-col">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-coral/10">
                <FileText className="h-5.5 w-5.5 text-coral" />
              </div>
              <h3 className="mt-3 text-base font-semibold text-navy">Reporte ejecutivo (PDF)</h3>
              <p className="mt-1 flex-1 text-sm leading-relaxed text-navy/60">
                Una página lista para compartir con tu equipo, tu socio o tu contador: KPIs,
                evolución, categorías y proyección con la marca de la plataforma.
              </p>
              {reportsLocked ? (
                <Link
                  to="/planes"
                  className="mt-4 inline-flex w-fit items-center gap-2 rounded-lg border border-gold/60 px-5 py-2.5 text-sm font-semibold text-gold transition-colors hover:bg-gold hover:text-navy-deep"
                >
                  <Lock className="h-4 w-4" /> Mejora a Analista para descargar
                </Link>
              ) : (
                <button
                  onClick={() => openPrintableReport(metrics, empresa)}
                  className="mt-4 inline-flex w-fit items-center gap-2 rounded-lg bg-teal px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal/90"
                >
                  <Printer className="h-4 w-4" /> Generar PDF
                </button>
              )}
              <p className="mt-2 text-xs text-navy/40">
                Se abre la vista de impresión: elige "Guardar como PDF".
              </p>
            </Card>

            {/* Excel / CSV */}
            <Card className="flex flex-col">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-green/10">
                <FileSpreadsheet className="h-5.5 w-5.5 text-green" />
              </div>
              <h3 className="mt-3 text-base font-semibold text-navy">Datos en Excel (CSV)</h3>
              <p className="mt-1 flex-1 text-sm leading-relaxed text-navy/60">
                Todas las tablas del dashboard en un archivo que Excel abre directo
                (formato es-CL): indicadores, evolución, categorías, canales, top productos
                y proyección.
              </p>
              {reportsLocked ? (
                <Link
                  to="/planes"
                  className="mt-4 inline-flex w-fit items-center gap-2 rounded-lg border border-gold/60 px-5 py-2.5 text-sm font-semibold text-gold transition-colors hover:bg-gold hover:text-navy-deep"
                >
                  <Lock className="h-4 w-4" /> Mejora a Analista para descargar
                </Link>
              ) : (
                <button
                  onClick={() => downloadReportCsv(metrics)}
                  className="mt-4 inline-flex w-fit items-center gap-2 rounded-lg border border-green/50 px-5 py-2.5 text-sm font-semibold text-green transition-colors hover:bg-green hover:text-white"
                >
                  <FileSpreadsheet className="h-4 w-4" /> Descargar Excel (CSV)
                </button>
              )}
              <p className="mt-2 text-xs text-navy/40">
                Separador ';' y codificación UTF-8 con BOM.
              </p>
            </Card>
          </div>
        </>
      )}
    </>
  )
}
