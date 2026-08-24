/**
 * Conectores (SPEC §7 — Fase 6, MVP).
 *
 * - Google Sheets (funcional): el usuario pega el enlace de una hoja pública o
 *   compartida por enlace; la API descarga el CSV oficial (sin OAuth) y el
 *   archivo entra al mismo pipeline que un Excel subido.
 * - Excel / CSV: enlace directo a Estandarización.
 * - Base de datos SQL y API/ERP: próximamente (requieren credenciales seguras).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
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
  RefreshCw,
  Table2,
  Trash2,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import { PlanRequiredModal } from '../components/ui/PlanGate'
import Badge from '../components/ui/Badge'
import { useDataset } from '../data/DatasetContext'
import { useFileImport } from '../data/useFileImport'
import { ApiError, apiDelete, apiGet, apiPostJson } from '../lib/api'

interface SheetsImportResponse {
  filename: string
  csv: string
  source_id: string | null
  content_hash: string
  persistent: boolean
}

interface SheetSource {
  id: string
  dataset_id: string | null
  source_url: string
  display_name: string
  gid: string
  sync_mode: 'manual' | 'automatic'
  update_available: boolean
  last_status: 'connected' | 'changed' | 'error'
  last_error: string | null
  last_checked_at: string | null
  last_synced_at: string | null
  created_at: string
}

interface SheetsRefreshResponse {
  source_id: string
  filename: string
  changed: boolean
  content_hash: string
  checked_at: string
  csv?: string
}

export default function Conectores() {
  const navigate = useNavigate()
  const { file, cleaning } = useDataset()
  const {
    importing,
    error: importError,
    persistWarning,
    importFile,
    planBlocked,
    dismissPlanBlocked,
    checkUploadAllowed,
    accessStatus,
  } = useFileImport()

  const [sheetUrl, setSheetUrl] = useState('')
  const [syncMode, setSyncMode] = useState<'manual' | 'automatic'>('automatic')
  const [fetching, setFetching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sources, setSources] = useState<SheetSource[]>([])
  const [sourcesAvailable, setSourcesAvailable] = useState(true)
  const [checkingSource, setCheckingSource] = useState<string | null>(null)
  const autoCheckedRef = useRef(new Set<string>())

  const working = fetching || importing
  const checkingAccess = accessStatus === 'loading'
  const busy = working || checkingAccess

  const handleImportSheet = async () => {
    const url = sheetUrl.trim()
    if (!url || busy) return
    // Fase 14: la puerta comercial va ANTES de POST /connectors/sheets —
    // antes la llamada salía primero y una cuenta sin plan recibía el 403
    // crudo en vez del modal comercial.
    if (!checkUploadAllowed()) return
    setError(null)
    setFetching(true)
    try {
      // La API valida la URL, extrae el ID y descarga el CSV oficial (≤15 MB)
      const result = await apiPostJson<SheetsImportResponse>('/connectors/sheets', { url, sync_mode: syncMode })
      const sheetFile = new File([result.csv], result.filename, { type: 'text/csv' })
      const ok = await importFile(sheetFile, { source: 'google_sheets', connectorSourceId: result.source_id })
      if (ok) {
        setSheetUrl('')
        void loadSources()
        navigate('/estandarizacion')
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo importar la hoja.')
    } finally {
      setFetching(false)
    }
  }

  const shownError = error ?? importError

  const loadSources = useCallback(async () => {
    try {
      const response = await apiGet<{ available: boolean; sources: SheetSource[] }>('/connectors/sheets/sources')
      setSourcesAvailable(response.available)
      setSources(response.sources)
    } catch {
      setSourcesAvailable(false)
      setSources([])
    }
  }, [])

  const checkSource = useCallback(async (source: SheetSource, applyUpdate: boolean) => {
    if (checkingSource || importing) return
    setCheckingSource(source.id)
    setError(null)
    try {
      const response = await apiPostJson<SheetsRefreshResponse>(`/connectors/sheets/sources/${source.id}/refresh`, { include_content: applyUpdate })
      if (applyUpdate && response.changed && response.csv != null) {
        const file = new File([response.csv], response.filename, { type: 'text/csv' })
        const ok = await importFile(file, { source: 'google_sheets', connectorSourceId: source.id })
        if (ok) navigate('/estandarizacion')
      }
      await loadSources()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo comprobar la fuente.')
      await loadSources()
    } finally {
      setCheckingSource(null)
    }
  }, [checkingSource, importing, importFile, loadSources, navigate])

  useEffect(() => { void loadSources() }, [loadSources])

  useEffect(() => {
    const automatic = sources.filter((source) => source.sync_mode === 'automatic' && !autoCheckedRef.current.has(source.id))
    const next = automatic[0]
    if (!next || checkingSource || importing) return
    autoCheckedRef.current.add(next.id)
    void checkSource(next, false)
  }, [sources, checkingSource, importing, checkSource])

  useEffect(() => {
    const interval = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return
      autoCheckedRef.current.clear()
      void loadSources()
    }, 5 * 60_000)
    return () => window.clearInterval(interval)
  }, [loadSources])

  const changeMode = async (source: SheetSource) => {
    const next = source.sync_mode === 'automatic' ? 'manual' : 'automatic'
    try {
      await apiPostJson(`/connectors/sheets/sources/${source.id}/mode`, { sync_mode: next })
      await loadSources()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cambiar la sincronización.')
    }
  }

  const removeSource = async (source: SheetSource) => {
    if (!window.confirm(`¿Desconectar “${source.display_name}”? Los datasets ya importados no se eliminan.`)) return
    try {
      await apiDelete(`/connectors/sheets/sources/${source.id}`)
      await loadSources()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo desconectar la fuente.')
    }
  }

  return (
    <>
      <PlanRequiredModal open={planBlocked} onClose={dismissPlanBlocked} />
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

      <div className="grid items-start gap-6 md:grid-cols-2">
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
                  Guarda uno o varios enlaces y detecta sus actualizaciones — sin instalar nada.
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
                disabled={working}
                className="w-full bg-transparent text-sm text-navy placeholder-navy/35 outline-none disabled:opacity-60"
              />
            </div>
            <button
              onClick={() => void handleImportSheet()}
              disabled={!sheetUrl.trim() || busy}
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-teal px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal/90 disabled:cursor-not-allowed disabled:bg-teal/50"
            >
              {checkingAccess ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Verificando acceso...
                </>
              ) : working ? (
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

          <label className="mt-3 inline-flex items-center gap-2 text-xs text-navy/60">
            <input type="checkbox" checked={syncMode === 'automatic'} onChange={(event) => setSyncMode(event.target.checked ? 'automatic' : 'manual')} className="h-4 w-4 rounded border-navy/20 text-teal focus:ring-teal" />
            Comprobar automáticamente si esta fuente cambia mientras uso la plataforma
          </label>

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
            Estandarización → Limpieza → Dashboard. Cada pestaña (gid) se registra por separado. Máximo 15 MB.
          </p>

          <div className="mt-5 border-t border-navy/10 pt-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div><h3 className="text-sm font-semibold text-navy">Fuentes conectadas</h3><p className="text-[11px] text-navy/45">Los cambios se detectan solos; tú decides cuándo volver a validar y aplicar la nueva versión.</p></div>
              <button onClick={() => void loadSources()} className="inline-flex items-center gap-1.5 rounded-lg border border-navy/15 px-3 py-1.5 text-[11px] font-semibold text-navy/60 hover:bg-navy/5"><RefreshCw className="h-3.5 w-3.5" /> Comprobar todas</button>
            </div>
            {!sourcesAvailable ? (
              <p className="mt-3 rounded-lg bg-gold/10 px-3 py-2 text-xs text-navy/60">La persistencia de conexiones se está habilitando. La importación directa sigue disponible.</p>
            ) : sources.length === 0 ? (
              <p className="mt-3 rounded-lg bg-navy/[0.03] px-3 py-4 text-center text-xs text-navy/45">Todavía no has guardado enlaces de Google Sheets.</p>
            ) : (
              <ul className="mt-3 grid gap-3 lg:grid-cols-2">
                {sources.map((source) => (
                  <li key={source.id} className={`rounded-xl border p-3.5 ${source.update_available ? 'border-gold/45 bg-gold/[0.06]' : source.last_status === 'error' ? 'border-coral/35 bg-coral/[0.04]' : 'border-navy/10 bg-white'}`}>
                    <div className="flex items-start gap-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-green/10"><Table2 className="h-4 w-4 text-green" /></div>
                      <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-navy">{source.display_name}</p><p className="mt-0.5 text-[10px] text-navy/40">Pestaña gid {source.gid} · {source.sync_mode === 'automatic' ? 'comprobación automática' : 'solo manual'}</p></div>
                      <button onClick={() => void removeSource(source)} className="rounded-md p-1 text-navy/30 hover:bg-coral/10 hover:text-coral" title="Desconectar"><Trash2 className="h-3.5 w-3.5" /></button>
                    </div>
                    {source.update_available ? <p className="mt-3 rounded-lg bg-gold/10 px-2.5 py-2 text-[11px] font-semibold text-navy/70">Hay cambios disponibles. Al actualizar volverás a Estandarización y Limpieza.</p> : source.last_error ? <p className="mt-3 text-[11px] text-coral">{source.last_error}</p> : <p className="mt-3 text-[11px] text-navy/45">Sin cambios pendientes.</p>}
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button onClick={() => void checkSource(source, source.update_available)} disabled={checkingSource === source.id || importing} className="inline-flex items-center gap-1.5 rounded-lg bg-teal px-3 py-1.5 text-[11px] font-semibold text-white disabled:opacity-50">{checkingSource === source.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}{source.update_available ? 'Actualizar datos' : 'Comprobar cambios'}</button>
                      <button onClick={() => void changeMode(source)} className="rounded-lg border border-navy/15 px-3 py-1.5 text-[10px] font-semibold text-navy/55 hover:bg-navy/5">{source.sync_mode === 'automatic' ? 'Pasar a manual' : 'Activar automática'}</button>
                      <a href={source.source_url} target="_blank" rel="noreferrer" className="ml-auto text-[10px] font-semibold text-teal hover:underline">Abrir en Google</a>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
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
