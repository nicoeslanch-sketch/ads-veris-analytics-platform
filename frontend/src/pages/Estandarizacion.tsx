import { useRef, useState } from 'react'
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
  const { file, standardization, uploadedAt, storagePath, setStandardization, sheet, setSheet } =
    useDataset()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [changingSheet, setChangingSheet] = useState(false)
  const [sheetError, setSheetError] = useState<string | null>(null)
  // Flujo compartido con Conectores: Storage + datasets + /standardize
  const { importing: processing, error, persistWarning, importFile } = useFileImport()

  const handleFile = async (selected: File) => {
    await importFile(selected)
  }

  // Fase 10 §8.3: el usuario elige la hoja del Excel y se re-estandariza.
  const availableSheets = standardization?.carga?.hojas_disponibles ?? []
  const activeSheet = sheet ?? standardization?.carga?.hoja_usada ?? null

  const changeSheet = async (name: string) => {
    if (!file || changingSheet || name === activeSheet) return
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
      <div className="flex items-start justify-between gap-4">
        <PageHeader
          title="Estandarización ✨"
          subtitle="Prepara tus datos unificando formatos, nombres y valores para que la limpieza funcione de mejor manera."
        />
        <Link
          to="/historial"
          className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-navy/20 bg-white px-4 py-2.5 text-sm font-medium text-navy transition-colors hover:bg-navy/5"
        >
          <History className="h-4 w-4" /> Historial de estandarizaciones
        </Link>
      </div>

      {/* Zona de carga + qué hace */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
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
            if (dropped && !processing) void handleFile(dropped)
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
            onClick={() => inputRef.current?.click()}
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

      {/* Selector de hoja (solo Excel con varias hojas) — Fase 10 §8.3 */}
      {availableSheets.length > 1 && (
        <Card className="mt-10 bg-gradient-to-r from-teal/[0.04] to-transparent">
          <div className="flex flex-wrap items-center gap-3">
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-navy">Hojas del archivo</h2>
              <p className="text-xs text-navy/55">
                Se eligió automáticamente la hoja con más datos; si tu base vive en otra
                hoja, selecciónala aquí (la limpieza y el dashboard se recalculan).
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {availableSheets.map((name) => (
                <button
                  key={name}
                  onClick={() => void changeSheet(name)}
                  disabled={changingSheet}
                  className={`rounded-lg border px-3.5 py-1.5 text-xs font-semibold transition-colors disabled:opacity-60 ${
                    name === activeSheet
                      ? 'border-teal bg-teal text-white'
                      : 'border-navy/20 bg-white text-navy hover:border-teal/60'
                  }`}
                >
                  {name}
                </button>
              ))}
              {changingSheet && <Loader2 className="h-4 w-4 animate-spin text-teal" />}
            </div>
          </div>
          {sheetError && (
            <p className="mt-3 rounded-lg border border-coral/40 bg-coral/5 px-3 py-2 text-xs text-coral">
              {sheetError}
            </p>
          )}
        </Card>
      )}

      {/* Archivos recientes + seguridad */}
      <div className="mt-10 grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
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
