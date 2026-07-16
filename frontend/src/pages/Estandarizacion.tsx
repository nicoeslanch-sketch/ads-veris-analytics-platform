import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileSpreadsheet,
  History,
  Loader2,
  ShieldCheck,
  Sparkles,
  Upload,
  UploadCloud,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import { PlanRequiredModal } from '../components/ui/PlanGate'
import Badge from '../components/ui/Badge'
import { useDataset } from '../data/DatasetContext'
import { useFileImport } from '../data/useFileImport'
import { ApiError, apiPost, buildDatasetForm } from '../lib/api'
import { formatDateTime, formatNumber } from '../lib/format'
import type { StandardizeResult } from '../lib/types'

const BENEFITS = [
  'Unifica nombres y textos duplicados',
  'Estandariza formatos de fechas y números',
  'Normaliza mayúsculas, minúsculas y tildes',
  'Prepara tus datos para una limpieza precisa',
]

const STEPS = [
  {
    n: 1,
    title: 'Sube tu archivo',
    text: 'Carga tu base de datos en Excel o CSV.',
    icon: Upload,
    tone: 'bg-green/10 text-green',
  },
  {
    n: 2,
    title: 'Estandarizamos tus datos',
    text: 'Aplicamos reglas inteligentes para unificar y normalizar la información.',
    icon: Sparkles,
    tone: 'bg-teal/10 text-teal',
  },
  {
    n: 3,
    title: 'Listo para limpieza',
    text: 'Tus datos estandarizados estarán disponibles en Limpieza de datos.',
    icon: CheckCircle2,
    tone: 'bg-gold/15 text-gold',
  },
]

export default function Estandarizacion() {
  const {
    file,
    standardization,
    uploadedAt,
    storagePath,
    setStandardization,
    sheet,
    setSheet,
    availableSheets,
    sheetSessions,
    combineSheets,
    setCombineSheets,
    reset,
  } = useDataset()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [changingSheet, setChangingSheet] = useState(false)
  const [sheetError, setSheetError] = useState<string | null>(null)
  // Flujo compartido con Conectores: Storage + datasets + /standardize
  const { importing: processing, error, persistWarning, importFile, planBlocked, dismissPlanBlocked, checkUploadAllowed } = useFileImport()

  const handleFile = async (selected: File) => {
    await importFile(selected)
  }

  // Fase 14: la puerta comercial se evalúa ANTES de abrir el selector — el
  // modal compacto intercepta el intento; ningún byte sale del navegador.
  const openFilePicker = () => {
    if (!checkUploadAllowed()) return
    inputRef.current?.click()
  }

  // Fase 10 §8.3: el usuario elige la hoja del Excel y se re-estandariza.
  const activeSheet = sheet ?? standardization?.carga?.hoja_usada ?? null
  const processedSheets = availableSheets.filter(
    (name) => Boolean(sheetSessions[name]?.standardization),
  )
  const processedColumnSets = processedSheets.map((name) =>
    [...(sheetSessions[name]?.standardization?.preview.columnas ?? [])].sort().join('\u0000'),
  )
  const canCombineSheets =
    processedColumnSets.length >= 2 &&
    processedColumnSets.every((columns) => columns === processedColumnSets[0])

  useEffect(() => {
    if (!canCombineSheets && combineSheets) setCombineSheets(false)
  }, [canCombineSheets, combineSheets, setCombineSheets])

  const changeSheet = async (name: string) => {
    if (!file || changingSheet || name === activeSheet) return
    if (sheetSessions[name]?.standardization) {
      setSheet(name)
      setSheetError(null)
      return
    }
    const previousSheet = sheet
    setChangingSheet(true)
    setSheetError(null)
    setSheet(name) // invalida limpieza/métricas: la hoja son otros datos
    try {
      const result = await apiPost<StandardizeResult>(
        '/standardize',
        buildDatasetForm(file, storagePath, { sheet: name }),
      )
      setStandardization(result)
    } catch (err) {
      // Fase 11: si la hoja falla, se vuelve a la anterior — el contexto no
      // puede quedar apuntando a una hoja que nunca se procesó.
      setSheet(previousSheet)
      setSheetError(
        err instanceof ApiError ? err.message : 'No se pudo procesar esa hoja.',
      )
    } finally {
      setChangingSheet(false)
    }
  }

  const totalChanges = standardization
    ? standardization.cambios.textos_normalizados +
      standardization.cambios.fechas_estandarizadas +
      standardization.cambios.numeros_estandarizados +
      standardization.cambios.encabezados_normalizados
    : 0

  return (
    <>
      <PlanRequiredModal open={planBlocked} onClose={dismissPlanBlocked} />
      <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <PageHeader
          className="!mb-0"
          title="Estandarización ✨"
          subtitle="Prepara tus datos unificando formatos, nombres y valores para que la limpieza funcione de mejor manera."
        />
        <Link
          to="/historial"
          className="inline-flex w-full shrink-0 items-center justify-center gap-2 rounded-lg border border-navy/20 bg-white px-4 py-2.5 text-sm font-medium text-navy transition-colors hover:bg-navy/5 sm:w-auto"
        >
          <History className="h-4 w-4" /> Historial de estandarizaciones
        </Link>
      </div>

      {/* Fase 11 §6.2: con un dataset activo, el usuario decide explícito si
          continúa con él o estandariza un documento NUEVO (nuevo registro en
          el Historial; el anterior queda guardado y se puede retomar). */}
      {file && standardization && (
        <div className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-teal/25 bg-teal/[0.06] px-4 py-3">
          <FileSpreadsheet className="h-5 w-5 shrink-0 text-teal" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-navy" title={file.name}>
              Dataset activo: {file.name}
            </p>
            <p className="text-xs text-navy/55">
              Ya está estandarizado{uploadedAt ? ` (${formatDateTime(uploadedAt)})` : ''}. Puedes
              continuar con él o partir con un documento nuevo.
            </p>
          </div>
          <div className="flex w-full min-w-0 flex-col gap-2 sm:w-auto sm:shrink-0 sm:flex-row sm:flex-wrap sm:items-center">
            <Link
              to="/limpieza"
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-teal px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-teal/90 sm:w-auto"
            >
              Continuar <ArrowRight className="h-3.5 w-3.5" />
            </Link>
            <button
              onClick={() => {
                if (!checkUploadAllowed()) return
                reset()
                inputRef.current?.click()
              }}
              className="inline-flex w-full min-w-0 items-center justify-center gap-1.5 whitespace-normal rounded-lg border border-navy/20 bg-white px-3 py-2 text-center text-xs font-semibold text-navy transition-colors hover:border-teal/60 sm:w-auto sm:px-4"
            >
              <UploadCloud className="h-3.5 w-3.5 shrink-0" /> Estandarizar nuevo documento
            </button>
          </div>
        </div>
      )}

      {/* Zona de carga + qué hace */}
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragOver(false)
            const dropped = e.dataTransfer.files?.[0]
            // Fase 14: la puerta va ANTES de leer el archivo soltado — sin
            // acceso, se abre el modal comercial y el archivo no se toca.
            if (dropped && !processing && checkUploadAllowed()) void handleFile(dropped)
          }}
          className={`flex flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed p-10 text-center transition-colors ${
            dragOver
              ? 'border-teal bg-teal/5'
              : 'border-navy/20 bg-gradient-to-b from-teal/[0.04] to-white'
          }`}
        >
          <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-teal/10">
            {processing ? (
              <Loader2 className="h-9 w-9 animate-spin text-teal" />
            ) : (
              <UploadCloud className="h-9 w-9 text-teal" />
            )}
          </div>
          <div>
            <h2 className="text-lg font-semibold text-navy">
              {processing ? 'Estandarizando tus datos...' : 'Sube tu archivo para estandarizarlo'}
            </h2>
            <p className="mx-auto mt-1 max-w-md text-sm text-navy/60">
              Unificamos nombres, formatos y valores para que tus datos estén listos para la
              limpieza y el análisis.
            </p>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.xlsx"
            className="hidden"
            onChange={(e) => {
              const selected = e.target.files?.[0]
              if (selected) void handleFile(selected)
              e.target.value = ''
            }}
          />
          <button
            onClick={openFilePicker}
            disabled={processing}
            className="inline-flex items-center gap-2 rounded-lg bg-teal px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal/90 disabled:cursor-not-allowed disabled:bg-teal/50"
          >
            <Upload className="h-4 w-4" />
            {processing ? 'Procesando...' : 'Subir archivo'}
          </button>
          <p className="text-xs text-navy/45">Formatos soportados: Excel (.xlsx), CSV (.csv)</p>
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-coral/40 bg-coral/10 px-4 py-3 text-left text-sm text-coral">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <p>{error}</p>
            </div>
          )}
          {persistWarning && (
            <div className="flex items-start gap-2 rounded-lg border border-gold/40 bg-gold/10 px-4 py-3 text-left text-sm text-navy/80">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
              <p>{persistWarning}</p>
            </div>
          )}
        </div>

        <Card className="h-fit bg-gradient-to-br from-gold/[0.06] to-transparent">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gold/15">
              <Sparkles className="h-4.5 w-4.5 text-gold" />
            </div>
            <h2 className="text-base font-semibold text-navy">¿Qué hace la estandarización?</h2>
          </div>
          <ul className="mt-4 space-y-3">
            {BENEFITS.map((benefit) => (
              <li key={benefit} className="flex items-start gap-2.5 text-sm text-navy/75">
                <CheckCircle2 className="mt-0.5 h-4.5 w-4.5 shrink-0 text-teal" />
                {benefit}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {/* Cómo funciona */}
      <div className="mt-10">
        <h2 className="text-lg font-semibold text-navy">Cómo funciona</h2>
        <p className="mt-0.5 text-sm text-navy/60">
          Un proceso simple en 3 pasos para dejar tus datos listos.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          {STEPS.map(({ n, title, text, icon: Icon, tone }, index) => (
            <Card
              key={n}
              className={`relative bg-gradient-to-br to-transparent ${
                index === 0 ? 'from-green/[0.05]' : index === 1 ? 'from-teal/[0.05]' : 'from-gold/[0.06]'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className={`flex h-10 w-10 items-center justify-center rounded-full ${tone}`}>
                  <Icon className="h-5 w-5" />
                </div>
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-navy text-xs font-bold text-white">
                  {n}
                </span>
              </div>
              <h3 className="mt-3 text-sm font-semibold text-navy">{title}</h3>
              <p className="mt-1 text-xs leading-relaxed text-navy/60">{text}</p>
            </Card>
          ))}
        </div>
      </div>

      {/* Fase 12 B5: cada pestaña conserva su propio estado; el manifiesto de
          descarga se construye desde este estado explícito, nunca del caché. */}
      {availableSheets.length > 1 && (
        <Card className="mt-10 overflow-hidden !p-0">
          <div className="px-5 pt-5">
            <h2 className="text-sm font-semibold text-navy">Hojas del archivo</h2>
            <p className="mt-1 text-xs text-navy/55">
              Abre cada hoja que quieras procesar. Cambiar de hoja no crea un documento
              nuevo y su configuración queda guardada por separado durante esta sesión.
            </p>
          </div>
          <div
            role="tablist"
            aria-label="Hojas del archivo Excel"
            className="mt-4 flex max-w-full gap-1 overflow-x-auto border-b border-navy/10 px-5"
          >
            {availableSheets.map((name) => {
              const processed = Boolean(sheetSessions[name]?.standardization)
              const selected = name === activeSheet
              return (
                <button
                  key={name}
                  role="tab"
                  aria-selected={selected}
                  onClick={() => void changeSheet(name)}
                  disabled={changingSheet}
                  className={`flex min-w-max items-center gap-2 border-b-2 px-3 py-3 text-xs font-semibold transition-colors disabled:opacity-60 ${
                    selected
                      ? 'border-teal text-teal'
                      : 'border-transparent text-navy/65 hover:border-navy/20 hover:text-navy'
                  }`}
                >
                  {changingSheet && selected ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : processed ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-green" />
                  ) : (
                    <span className="h-2.5 w-2.5 rounded-full border border-navy/35" />
                  )}
                  <span>{name}</span>
                  <span className="font-normal text-navy/45">
                    {processed ? 'Procesada' : 'Sin procesar'}
                  </span>
                </button>
              )
            })}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
            <p className="text-xs text-navy/60">
              Estás viendo: <strong className="text-navy">{activeSheet ?? '—'}</strong>
            </p>
            {canCombineSheets && (
              <label className="flex cursor-pointer items-start gap-2 text-xs text-navy">
                <input
                  type="checkbox"
                  checked={combineSheets}
                  onChange={(event) => setCombineSheets(event.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-teal"
                />
                <span>
                  <strong>Combinar {processedSheets.length} hojas compatibles</strong>
                  <span className="block text-navy/50">
                    Crea una base adicional con la columna hoja_origen.
                  </span>
                </span>
              </label>
            )}
          </div>
          {processedSheets.length >= 2 && !canCombineSheets && (
            <p className="border-t border-gold/20 bg-gold/[0.06] px-5 py-3 text-xs text-navy/65">
              Estas hojas tienen estructuras distintas. No se unirán automáticamente:
              relacionarlas requiere que indiques una clave común.
            </p>
          )}
          {sheetError && (
            <p className="border-t border-coral/30 bg-coral/5 px-5 py-3 text-xs text-coral">
              {sheetError}
            </p>
          )}
        </Card>
      )}

      {/* Archivos recientes + seguridad */}
      <div className="mt-10 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="min-w-0">
          <h2 className="text-base font-semibold text-navy">
            Archivos estandarizados recientes
          </h2>
          {standardization && file ? (
            <>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-navy/10 text-left text-xs font-semibold uppercase tracking-wide text-navy/50">
                      <th className="pb-2 pr-4">Archivo</th>
                      <th className="pb-2 pr-4">Fecha</th>
                      <th className="pb-2 pr-4">Registros</th>
                      <th className="pb-2 pr-4">Cambios</th>
                      <th className="pb-2 pr-4">Estado</th>
                      <th className="pb-2">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-navy/5">
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2 font-medium text-navy">
                          <FileSpreadsheet className="h-4.5 w-4.5 text-green" />
                          {standardization.archivo}
                        </div>
                      </td>
                      <td className="py-3 pr-4 text-navy/70">
                        {uploadedAt ? formatDateTime(uploadedAt) : '—'}
                      </td>
                      <td className="py-3 pr-4 text-navy/70">
                        {formatNumber(standardization.filas)}
                      </td>
                      <td className="py-3 pr-4 text-navy/70">{formatNumber(totalChanges)}</td>
                      <td className="py-3 pr-4">
                        <Badge tone="green">
                          <CheckCircle2 className="h-3 w-3" /> Estandarizado
                        </Badge>
                      </td>
                      <td className="py-3">
                        <Link
                          to="/limpieza"
                          className="inline-flex items-center gap-1.5 rounded-lg border border-teal/50 px-3 py-1.5 text-xs font-semibold text-teal transition-colors hover:bg-teal hover:text-white"
                        >
                          Continuar a Limpieza <ArrowRight className="h-3.5 w-3.5" />
                        </Link>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs text-navy/50">
                {formatNumber(standardization.cambios.textos_normalizados)} textos unificados ·{' '}
                {formatNumber(standardization.cambios.fechas_estandarizadas)} fechas
                estandarizadas · {formatNumber(standardization.cambios.numeros_estandarizados)}{' '}
                números normalizados
              </p>
            </>
          ) : (
            <p className="mt-4 text-sm text-navy/50">
              Todavía no has estandarizado archivos en esta sesión. Sube tu primer Excel o CSV
              para empezar.
            </p>
          )}
        </Card>

        <Card className="h-fit border-green/25 bg-green/5">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-green/15">
              <ShieldCheck className="h-5 w-5 text-green" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-navy">Tus datos seguros</h3>
              <p className="mt-1 text-xs leading-relaxed text-navy/60">
                Tus archivos se almacenan cifrados en tu cuenta y solo tú puedes verlos.
                Al asistente IA se le envían únicamente indicadores agregados (totales y
                resúmenes), nunca tu archivo completo. No vendemos ni compartimos tus
                datos con fines comerciales.
              </p>
            </div>
          </div>
        </Card>
      </div>
    </>
  )
}
