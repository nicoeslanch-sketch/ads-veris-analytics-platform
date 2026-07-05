import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  Bookmark,
  CalendarClock,
  CheckCircle2,
  Columns3,
  Copy,
  Crown,
  Download,
  Eraser,
  FileSpreadsheet,
  FileWarning,
  Loader2,
  Rows3,
  Settings2,
  Sparkles,
  Type,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import EmptyState from '../components/ui/EmptyState'
import Toggle from '../components/ui/Toggle'
import { useDataset } from '../data/DatasetContext'
import { apiPost, apiDownload, buildDatasetForm, ApiError } from '../lib/api'
import { saveCleaningJob } from '../lib/datasets'
import { supabaseConfigured } from '../lib/supabase'
import { formatNumber } from '../lib/format'
import { DEFAULT_RULES, type CleanResult, type CleaningRules } from '../lib/types'

const RULE_LABELS: Array<{ key: keyof CleaningRules; label: string }> = [
  { key: 'fechas', label: 'Estándar de formato de fecha' },
  { key: 'textos', label: 'Unificar texto' },
  { key: 'duplicados', label: 'Eliminar duplicados' },
  { key: 'tipos', label: 'Convertir tipos de dato' },
  { key: 'nulos', label: 'Manejar valores nulos' },
  { key: 'columnas_vacias', label: 'Eliminar columnas vacías' },
  { key: 'fuera_de_rango', label: 'Validar rangos y outliers' },
]

const PROBLEM_LABELS: Array<{
  key: keyof CleanResult['problemas']
  label: string
  icon: typeof Copy
}> = [
  { key: 'duplicados', label: 'Duplicados', icon: Copy },
  { key: 'valores_nulos', label: 'Valores nulos', icon: FileWarning },
  { key: 'fechas_invalidas', label: 'Formatos de fecha inválidos', icon: CalendarClock },
  { key: 'textos_inconsistentes', label: 'Textos inconsistentes', icon: Type },
  { key: 'tipos_incorrectos', label: 'Tipos de datos incorrectos', icon: Settings2 },
  { key: 'columnas_vacias', label: 'Columnas vacías', icon: Columns3 },
  { key: 'valores_fuera_de_rango', label: 'Valores fuera de rango', icon: AlertTriangle },
]

function qualityLabel(quality: number): { text: string; tone: 'green' | 'gold' | 'coral' } {
  if (quality >= 90) return { text: 'Excelente', tone: 'green' }
  if (quality >= 75) return { text: 'Buena', tone: 'green' }
  if (quality >= 50) return { text: 'Regular', tone: 'gold' }
  return { text: 'Baja', tone: 'coral' }
}

function QualityRing({ quality }: { quality: number }) {
  const radius = 26
  const circumference = 2 * Math.PI * radius
  const filled = (quality / 100) * circumference
  const color = quality >= 75 ? 'var(--color-green)' : quality >= 50 ? 'var(--color-gold)' : 'var(--color-coral)'
  return (
    <div className="relative h-16 w-16">
      <svg viewBox="0 0 64 64" className="h-16 w-16 -rotate-90">
        <circle cx="32" cy="32" r={radius} fill="none" stroke="#e8edf0" strokeWidth="7" />
        <circle
          cx="32"
          cy="32"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference - filled}`}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-navy">
        {Math.round(quality)}%
      </span>
    </div>
  )
}

export default function Limpieza() {
  const { file, datasetId, storagePath, standardization, cleaning, setCleaning } = useDataset()
  const [detection, setDetection] = useState<CleanResult | null>(null)
  const [rules, setRules] = useState<CleaningRules>(DEFAULT_RULES)
  const [detecting, setDetecting] = useState(false)
  const [applying, setApplying] = useState(false)
  const [downloading, setDownloading] = useState<'xlsx' | 'csv' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [persistWarning, setPersistWarning] = useState<string | null>(null)
  const detectStartedFor = useRef<File | null>(null)

  useEffect(() => {
    if (!file || cleaning || detectStartedFor.current === file) return
    detectStartedFor.current = file
    setDetecting(true)
    setError(null)
    apiPost<CleanResult>('/clean', buildDatasetForm(file, storagePath, { apply: 'false' }))
      .then(setDetection)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'No se pudo analizar el archivo.'),
      )
      .finally(() => setDetecting(false))
  }, [file, storagePath, cleaning])

  if (!file || !standardization) {
    return (
      <>
        <PageHeader
          title="Limpieza de datos ✨"
          subtitle="Revisa, ajusta y limpia tus datos para que estén listos para el análisis."
        />
        <EmptyState
          icon={Sparkles}
          title="No hay archivos para limpiar"
          description="Primero estandariza un archivo. Después podrás revisar los problemas detectados (duplicados, nulos, formatos inválidos) y aplicar la limpieza."
          ctaLabel="Ir a Estandarización"
          ctaTo="/estandarizacion"
        />
      </>
    )
  }

  const result = cleaning ?? detection
  const applied = cleaning !== null
  const totalProblems = result
    ? PROBLEM_LABELS.reduce((sum, { key }) => sum + result.problemas[key], 0)
    : 0
  const quality = result
    ? applied
      ? result.resumen.calidad_despues
      : result.resumen.calidad_antes
    : null

  // Qué se corregirá según los toggles activos (mismo cálculo que hace la API).
  const planned = result
    ? [
        { label: 'Filas duplicadas a eliminar', value: rules.duplicados ? result.problemas.duplicados : 0 },
        { label: 'Valores nulos a reemplazar', value: rules.nulos ? result.problemas.valores_nulos : 0 },
        {
          label: 'Fechas a estandarizar',
          value:
            result.estandarizacion.fechas_estandarizadas +
            (rules.fechas ? result.problemas.fechas_invalidas : 0),
        },
        { label: 'Textos a unificar', value: rules.textos ? result.problemas.textos_inconsistentes : 0 },
        { label: 'Tipos de datos a corregir', value: rules.tipos ? result.problemas.tipos_incorrectos : 0 },
        { label: 'Columnas vacías a eliminar', value: rules.columnas_vacias ? result.problemas.columnas_vacias : 0 },
        { label: 'Valores fuera de rango a revisar', value: rules.fuera_de_rango ? result.problemas.valores_fuera_de_rango : 0 },
      ]
    : []

  const issueMap = new Map<string, string>()
  if (result && !applied) {
    for (const issue of result.preview.issues) {
      issueMap.set(`${issue.fila}:${issue.columna}`, issue.tipo)
    }
  }

  const handleDownload = async (fmt: 'xlsx' | 'csv') => {
    if (!file) return
    setDownloading(fmt)
    setError(null)
    try {
      const stem = file.name.replace(/\.[^.]+$/, '')
      await apiDownload(
        '/clean/download',
        buildDatasetForm(file, storagePath, { rules: JSON.stringify(rules), fmt }),
        `${stem}_limpio.${fmt}`,
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo descargar el archivo.')
    } finally {
      setDownloading(null)
    }
  }

  const handleApply = async () => {
    setApplying(true)
    setError(null)
    setPersistWarning(null)
    try {
      const response = await apiPost<CleanResult>(
        '/clean',
        buildDatasetForm(file, storagePath, { apply: 'true', rules: JSON.stringify(rules) }),
      )
      setCleaning(response)
      // Best-effort: si falla el guardado, la limpieza IGUAL quedó aplicada —
      // jamás mostrarlo como error de limpieza (solo aviso de historial).
      const saved = await saveCleaningJob(datasetId, rules, response)
      if (!saved && supabaseConfigured && datasetId) {
        setPersistWarning(
          'La limpieza se aplicó correctamente, pero no se pudo guardar en el historial.',
        )
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo aplicar la limpieza.')
    } finally {
      setApplying(false)
    }
  }

  const steps = [
    { title: 'Cargar datos', text: 'Archivo cargado correctamente', done: true },
    {
      title: 'Revisar problemas',
      text: result ? `${formatNumber(totalProblems)} problemas detectados` : 'Analizando...',
      done: result !== null,
      warn: result !== null && totalProblems > 0 && !applied,
    },
    { title: 'Configurar reglas', text: 'Reglas automáticas activas', done: true },
    { title: 'Aplicar limpieza', text: applied ? 'Limpieza aplicada' : 'Aún no ejecutado', done: applied },
    { title: 'Dataset limpio', text: applied ? 'Listo para el análisis' : 'Pendiente', done: applied },
  ]

  return (
    <>
      <div className="flex items-start justify-between gap-4">
        <PageHeader
          title="Limpieza de datos ✨"
          subtitle="Revisa, ajusta y limpia tus datos para que estén listos para el análisis."
        />
        <Link
          to="/historial"
          className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-navy/20 bg-white px-4 py-2.5 text-sm font-medium text-navy transition-colors hover:bg-navy/5"
        >
          <CalendarClock className="h-4 w-4" /> Historial de cargas
        </Link>
      </div>

      {/* Encabezado: archivo, filas, columnas, calidad, estado */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Card className="!p-4">
          <div className="flex items-start gap-3">
            <FileSpreadsheet className="mt-0.5 h-8 w-8 shrink-0 text-green" />
            <div className="min-w-0">
              <p className="text-xs text-navy/50">Archivo actual</p>
              <p className="truncate text-sm font-semibold text-navy" title={file.name}>
                {file.name}
              </p>
              <Link to="/estandarizacion" className="text-xs font-medium text-teal hover:underline">
                Cambiar archivo
              </Link>
            </div>
          </div>
        </Card>
        <Card className="!p-4">
          <div className="flex items-start gap-3">
            <Rows3 className="mt-0.5 h-8 w-8 shrink-0 text-teal" />
            <div>
              <p className="text-xs text-navy/50">Filas</p>
              <p className="text-xl font-bold text-navy">
                {formatNumber(applied && result ? result.resumen.filas_despues : standardization.filas)}
              </p>
              <p className="text-xs text-navy/50">Registros totales</p>
            </div>
          </div>
        </Card>
        <Card className="!p-4">
          <div className="flex items-start gap-3">
            <Columns3 className="mt-0.5 h-8 w-8 shrink-0 text-navy/70" />
            <div>
              <p className="text-xs text-navy/50">Columnas</p>
              <p className="text-xl font-bold text-navy">
                {formatNumber(applied && result ? result.resumen.columnas_despues : standardization.columnas)}
              </p>
              <p className="text-xs text-navy/50">Variables detectadas</p>
            </div>
          </div>
        </Card>
        <Card className="!p-4">
          <div className="flex items-center gap-3">
            {quality !== null ? <QualityRing quality={quality} /> : <Loader2 className="h-8 w-8 animate-spin text-teal" />}
            <div>
              <p className="text-xs text-navy/50">Calidad del dato</p>
              {quality !== null && (
                <Badge tone={qualityLabel(quality).tone}>{qualityLabel(quality).text}</Badge>
              )}
            </div>
          </div>
        </Card>
        <Card className="!p-4">
          <div className="flex items-start gap-3">
            <CheckCircle2 className={`mt-0.5 h-8 w-8 shrink-0 ${applied ? 'text-green' : 'text-gold'}`} />
            <div>
              <p className="text-xs text-navy/50">Estado</p>
              <p className="text-sm font-semibold text-navy">
                {applied ? 'Dataset limpio' : 'Listo para limpiar'}
              </p>
              <p className="text-xs text-navy/50">
                {applied
                  ? 'Limpieza aplicada correctamente.'
                  : 'Se detectaron problemas que puedes revisar.'}
              </p>
            </div>
          </div>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[260px_minmax(0,1fr)]">
        {/* Columna izquierda: pasos + premium */}
        <div className="space-y-6">
          <Card>
            <h2 className="text-sm font-semibold text-navy">Pasos de limpieza</h2>
            <ol className="mt-4 space-y-3">
              {steps.map((step, index) => (
                <li key={step.title} className="flex items-start gap-3">
                  <span
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                      step.done
                        ? 'bg-green/15 text-green'
                        : step.warn
                          ? 'bg-gold/20 text-gold'
                          : 'bg-navy/10 text-navy/50'
                    }`}
                  >
                    {step.done ? <CheckCircle2 className="h-4 w-4" /> : index + 1}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-navy">{step.title}</p>
                    <p className="text-xs text-navy/55">{step.text}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Card>

          <Card className="border-gold/40 bg-gold/5">
            <div className="flex items-center gap-2">
              <Crown className="h-4.5 w-4.5 text-gold" />
              <h2 className="text-sm font-semibold text-navy">Limpieza personalizada</h2>
              <Badge tone="gold">Premium</Badge>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-navy/60">
              Aplica reglas y variables personalizadas para una limpieza a tu medida, con
              instrucciones en lenguaje natural. Disponible en el plan Gold (Fase 3).
            </p>
            <button
              disabled
              className="mt-3 w-full cursor-not-allowed rounded-lg bg-gold/80 px-4 py-2 text-sm font-semibold text-navy-deep opacity-70"
            >
              Extender mi plan
            </button>
          </Card>
        </div>

        {/* Columna principal */}
        <div className="min-w-0 space-y-6">
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-coral/40 bg-coral/10 px-4 py-3 text-sm text-coral">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <p>{error}</p>
            </div>
          )}
          {persistWarning && (
            <div className="flex items-start gap-2 rounded-lg border border-gold/40 bg-gold/10 px-4 py-3 text-sm text-navy/80">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
              <p>{persistWarning}</p>
            </div>
          )}

          {applied && result ? (
            <Card className="border-green/30 bg-green/5">
              <div className="flex items-start gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-green/15">
                  <CheckCircle2 className="h-6 w-6 text-green" />
                </div>
                <div className="flex-1">
                  <h2 className="text-base font-semibold text-navy">Limpieza aplicada ✅</h2>
                  <p className="mt-1 text-sm text-navy/70">
                    Tu dataset quedó limpio y cargado para el resto de los módulos. La calidad
                    subió de <strong>{result.resumen.calidad_antes}%</strong> a{' '}
                    <strong>{result.resumen.calidad_despues}%</strong>. Filas:{' '}
                    {formatNumber(result.resumen.filas_antes)} →{' '}
                    {formatNumber(result.resumen.filas_despues)} · Columnas:{' '}
                    {formatNumber(result.resumen.columnas_antes)} →{' '}
                    {formatNumber(result.resumen.columnas_despues)}.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      onClick={() => void handleDownload('xlsx')}
                      disabled={downloading !== null}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-teal/10 px-3 py-1.5 text-xs font-semibold text-teal transition-colors hover:bg-teal/20 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {downloading === 'xlsx' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                      Descargar Excel
                    </button>
                    <button
                      onClick={() => void handleDownload('csv')}
                      disabled={downloading !== null}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-navy/5 px-3 py-1.5 text-xs font-semibold text-navy/70 transition-colors hover:bg-navy/10 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {downloading === 'csv' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                      Descargar CSV
                    </button>
                  </div>
                </div>
              </div>
            </Card>
          ) : (
            <>
              {/* Vista previa con errores resaltados */}
              <Card>
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="text-base font-semibold text-navy">
                    Vista previa de los datos originales
                  </h2>
                  <Badge tone="gold">Antes de la limpieza</Badge>
                </div>
                {detecting || !result ? (
                  <div className="flex items-center gap-3 py-10 text-sm text-navy/60">
                    <Loader2 className="h-5 w-5 animate-spin text-teal" />
                    Analizando problemas del archivo...
                  </div>
                ) : (
                  <>
                    <div className="mt-4 overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-navy/10 text-left font-semibold text-navy/60">
                            <th className="py-2 pr-3">#</th>
                            {result.preview.columnas.map((col) => (
                              <th key={col} className="py-2 pr-4 whitespace-nowrap">
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {result.preview.filas.map((row, rowIndex) => {
                            const isDuplicate = issueMap.get(`${rowIndex}:*`) === 'duplicado'
                            return (
                              <tr
                                key={rowIndex}
                                className={`border-b border-navy/5 ${isDuplicate ? 'bg-coral/5' : ''}`}
                              >
                                <td className="py-2 pr-3 text-navy/40">{rowIndex + 1}</td>
                                {row.map((cell, colIndex) => {
                                  const column = result.preview.columnas[colIndex]
                                  const issue = issueMap.get(`${rowIndex}:${column}`)
                                  return (
                                    <td
                                      key={colIndex}
                                      className={`py-2 pr-4 whitespace-nowrap ${
                                        issue
                                          ? 'font-semibold text-coral'
                                          : isDuplicate
                                            ? 'text-coral/80'
                                            : 'text-navy/75'
                                      }`}
                                      title={issue ? `Problema: ${issue.replace('_', ' ')}` : undefined}
                                    >
                                      {cell || '—'}
                                    </td>
                                  )
                                })}
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                    <div className="mt-4 flex items-start gap-2 rounded-lg border border-gold/40 bg-gold/10 px-4 py-3 text-sm text-navy">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
                      <p>
                        Detectamos <strong>{formatNumber(totalProblems)} problemas</strong> en tus
                        datos que puedes revisar y corregir antes de continuar.
                      </p>
                    </div>
                  </>
                )}
              </Card>

              {/* Problemas / correcciones / reglas */}
              {result && (
                <div className="grid gap-6 md:grid-cols-2 2xl:grid-cols-3">
                  <Card>
                    <div className="flex items-center gap-2">
                      <FileWarning className="h-4.5 w-4.5 text-coral" />
                      <h3 className="text-sm font-semibold text-navy">Problemas detectados</h3>
                    </div>
                    <ul className="mt-4 space-y-2.5">
                      {PROBLEM_LABELS.map(({ key, label, icon: Icon }) => (
                        <li key={key} className="flex items-center justify-between gap-2 text-sm">
                          <span className="flex items-center gap-2 text-navy/70">
                            <Icon className="h-4 w-4 text-navy/40" /> {label}
                          </span>
                          <span
                            className={`font-semibold ${
                              result.problemas[key] > 0 ? 'text-coral' : 'text-navy/40'
                            }`}
                          >
                            {formatNumber(result.problemas[key])}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </Card>

                  <Card>
                    <div className="flex items-center gap-2">
                      <Eraser className="h-4.5 w-4.5 text-teal" />
                      <h3 className="text-sm font-semibold text-navy">
                        Qué se eliminará / corregirá
                      </h3>
                    </div>
                    <ul className="mt-4 space-y-2.5">
                      {planned.map(({ label, value }) => (
                        <li key={label} className="flex items-center justify-between gap-2 text-sm">
                          <span className="text-navy/70">{label}</span>
                          <span className={`font-semibold ${value > 0 ? 'text-teal' : 'text-navy/40'}`}>
                            {formatNumber(value)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </Card>

                  <Card>
                    <div className="flex items-center gap-2">
                      <Settings2 className="h-4.5 w-4.5 text-navy/60" />
                      <h3 className="text-sm font-semibold text-navy">Reglas activas (automáticas)</h3>
                    </div>
                    <ul className="mt-4 space-y-3">
                      {RULE_LABELS.map(({ key, label }) => (
                        <li key={key} className="flex items-center justify-between gap-2 text-sm">
                          <span className="text-navy/70">{label}</span>
                          <Toggle
                            checked={rules[key]}
                            label={label}
                            onChange={(value) => setRules((prev) => ({ ...prev, [key]: value }))}
                          />
                        </li>
                      ))}
                    </ul>
                  </Card>
                </div>
              )}
            </>
          )}

          {/* Barra de acción */}
          <Card className="!p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <button
                disabled
                className="inline-flex cursor-not-allowed items-center gap-2 rounded-lg border border-navy/15 px-4 py-2 text-sm font-medium text-navy/40"
              >
                <Bookmark className="h-4 w-4" /> Guardar como borrador
              </button>
              <p className="text-sm text-navy/55">
                {applied
                  ? 'La limpieza fue aplicada. Tus datos están listos.'
                  : 'La limpieza aún no ha sido aplicada.'}
              </p>
              {applied ? (
                <Link
                  to="/explorar"
                  className="inline-flex items-center gap-2 rounded-lg bg-navy px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-navy-deep"
                >
                  Continuar <ArrowRight className="h-4 w-4" />
                </Link>
              ) : (
                <button
                  onClick={() => void handleApply()}
                  disabled={applying || detecting || !result}
                  className="inline-flex items-center gap-2 rounded-lg bg-teal px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal/90 disabled:cursor-not-allowed disabled:bg-teal/50"
                >
                  {applying ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" /> Aplicando...
                    </>
                  ) : (
                    <>
                      Aplicar limpieza y continuar <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </button>
              )}
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
