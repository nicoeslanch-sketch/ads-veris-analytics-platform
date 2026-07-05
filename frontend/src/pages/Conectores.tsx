/**
 * Conectores (SPEC §7 — Fase 6, MVP).
 *
 * - Google Sheets (funcional): el usuario pega el enlace de una hoja pública o
 *   compartida por enlace; la API descarga el CSV oficial (sin OAuth) y el
 *   archivo entra al mismo pipeline que un Excel subido.
 * - Excel / CSV: enlace directo a Estandarización.
 * - Base de datos SQL y API/ERP: próximamente (requieren credenciales seguras).
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Database,
  FileSpreadsheet,
  Link2,
  Loader2,
  Plug,
  Table2,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import { useDataset } from '../data/DatasetContext'
import { useFileImport } from '../data/useFileImport'
import { ApiError, apiPostJson } from '../lib/api'

interface SheetsImportResponse {
  filename: string
  csv: string
}

export default function Conectores() {
  const navigate = useNavigate()
  const { file, cleaning } = useDataset()
  const { importing, error: importError, persistWarning, importFile } = useFileImport()

  const [sheetUrl, setSheetUrl] = useState('')
  const [fetching, setFetching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const busy = fetching || importing

  const handleImportSheet = async () => {
    const url = sheetUrl.trim()
    if (!url || busy) return
    setError(null)
    setFetching(true)
    try {
      // La API valida la URL, extrae el ID y descarga el CSV oficial (≤15 MB)
      const result = await apiPostJson<SheetsImportResponse>('/connectors/sheets', { url })
      const sheetFile = new File([result.csv], result.filename, { type: 'text/csv' })
      const ok = await importFile(sheetFile, { source: 'google_sheets' })
      if (ok) navigate('/estandarizacion')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo importar la hoja.')
    } finally {
      setFetching(false)
    }
  }

  const shownError = error ?? importError

  return (
    <>
      <PageHeader
        title="Conectores"
        subtitle="Conecta tus fuentes de datos: archivos Excel/CSV, Google Sheets y próximamente bases SQL."
      />

      {/* Fuente activa de la sesión */}
      {file && (
        <Card className="mb-6 border-green/25 bg-green/5">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="h-5 w-5 shrink-0 text-green" />
            <p className="text-sm text-navy/75">
              Fuente activa de la sesión:{' '}
              <span className="font-semibold text-navy">{file.name}</span>{' '}
              {cleaning ? '(dataset limpio)' : '(pendiente de limpieza)'}
            </p>
          </div>
        </Card>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        {/* Google Sheets — funcional */}
        <Card className="md:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-green/10">
                <Table2 className="h-5.5 w-5.5 text-green" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-navy">Google Sheets</h2>
                <p className="text-xs text-navy/55">
                  Importa una hoja pública o compartida por enlace — sin instalar nada.
                </p>
              </div>
            </div>
            <Badge tone="green">Disponible</Badge>
          </div>

          <div className="mt-4 flex flex-col gap-3 sm:flex-row">
            <div className="flex flex-1 items-center gap-2 rounded-lg border border-navy/20 bg-white px-3 py-2 focus-within:border-teal">
              <Link2 className="h-4 w-4 shrink-0 text-navy/40" />
              <input
                value={sheetUrl}
                onChange={(e) => {
                  setSheetUrl(e.target.value)
                  setError(null)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void handleImportSheet()
                }}
                placeholder="https://docs.google.com/spreadsheets/d/..."
                disabled={busy}
                className="w-full bg-transparent text-sm text-navy placeholder-navy/35 outline-none disabled:opacity-60"
              />
            </div>
            <button
              onClick={() => void handleImportSheet()}
              disabled={!sheetUrl.trim() || busy}
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-teal px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal/90 disabled:cursor-not-allowed disabled:bg-teal/50"
            >
              {busy ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {fetching ? 'Descargando…' : 'Estandarizando…'}
                </>
              ) : (
                <>
                  Importar <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </div>

          {shownError && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-coral/40 bg-coral/10 px-3 py-2.5 text-sm text-coral">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <p>{shownError}</p>
            </div>
          )}
          {persistWarning && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-gold/40 bg-gold/10 px-3 py-2.5 text-sm text-navy/80">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
              <p>{persistWarning}</p>
            </div>
          )}

          <p className="mt-3 text-xs leading-relaxed text-navy/50">
            La hoja debe estar compartida como{' '}
            <span className="font-medium text-navy/70">
              "Cualquier persona con el enlace"
            </span>{' '}
            (como lector). Tras importar, el archivo sigue el mismo flujo:
            Estandarización → Limpieza → Dashboard. Máximo 15 MB.
          </p>
        </Card>

        {/* Excel / CSV */}
        <Card>
          <div className="flex items-center justify-between">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-teal/10">
              <FileSpreadsheet className="h-5.5 w-5.5 text-teal" />
            </div>
            <Badge tone="green">Disponible</Badge>
          </div>
          <h2 className="mt-3 text-base font-semibold text-navy">Excel / CSV</h2>
          <p className="mt-1 text-sm leading-relaxed text-navy/60">
            Sube archivos .xlsx o .csv directo desde tu computador, con drag &amp; drop.
          </p>
          <button
            onClick={() => navigate('/estandarizacion')}
            className="mt-4 inline-flex items-center gap-2 rounded-lg border border-teal/50 px-4 py-2 text-sm font-semibold text-teal transition-colors hover:bg-teal hover:text-white"
          >
            Cargar un archivo <ArrowRight className="h-4 w-4" />
          </button>
        </Card>

        {/* SQL — próximamente */}
        <Card className="opacity-80">
          <div className="flex items-center justify-between">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-navy/10">
              <Database className="h-5.5 w-5.5 text-navy/60" />
            </div>
            <Badge tone="gold">Próximamente</Badge>
          </div>
          <h2 className="mt-3 text-base font-semibold text-navy">Base de datos SQL</h2>
          <p className="mt-1 text-sm leading-relaxed text-navy/60">
            Conexión directa a MySQL/PostgreSQL de tu sistema de ventas o ERP, con
            sincronización programada. Requiere manejo seguro de credenciales.
          </p>
        </Card>

        {/* API / otros — próximamente */}
        <Card className="opacity-80 md:col-span-2">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-navy/10">
              <Plug className="h-5.5 w-5.5 text-navy/60" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-navy">Otras integraciones</h2>
                <Badge tone="gold">Próximamente</Badge>
              </div>
              <p className="mt-0.5 text-sm text-navy/60">
                Punto de venta, facturación electrónica y e-commerce (Bsale, Defontana,
                Jumpseller, Shopify). Cuéntanos cuál usas para priorizarla.
              </p>
            </div>
          </div>
        </Card>
      </div>
    </>
  )
}
