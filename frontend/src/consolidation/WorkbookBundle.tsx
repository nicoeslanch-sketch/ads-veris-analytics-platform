import { useEffect, useRef, useState } from 'react'
import { Download, FileSpreadsheet, Plus, X } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import AnalysisLoadingPanel from '../components/AnalysisLoadingPanel'
import { apiDownload } from '../lib/api'

export default function WorkbookBundle() {
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])

  function addFiles(selected: File[]) {
    const next = [...files, ...selected]
    setDone(false)
    if (next.some(file => !file.name.toLowerCase().endsWith('.xlsx'))) {
      setError('Selecciona archivos Excel .xlsx.'); return
    }
    if (next.length > 10 || next.reduce((total, file) => total + file.size, 0) > 15 * 1024 * 1024) {
      setError('Puedes unir hasta 10 archivos y 15 MB en total.'); return
    }
    setError('')
    setFiles(next)
  }

  async function download() {
    const controller = new AbortController()
    request.current = controller
    setBusy(true); setError(''); setDone(false)
    const form = new FormData()
    files.forEach(file => form.append('files', file))
    try {
      await apiDownload('/consolidation/workbook', form, 'Archivos_unidos.xlsx', { signal: controller.signal, timeoutMs: 120_000 })
      if (!controller.signal.aborted) setDone(true)
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'No se pudo unir los archivos.')
    } finally {
      if (request.current === controller) { request.current = null; setBusy(false) }
    }
  }

  return <section className="min-w-0">
    <PageHeader title="Consolidar archivos" subtitle="Un Excel con todas las hojas de tus archivos." />
    <p className="mb-5 max-w-3xl text-sm text-navy/70">Se conservan los datos, los resultados guardados y los formatos de fechas y números. No se copian fórmulas, gráficos ni diseños. Los originales no cambian.</p>
    <input ref={input} type="file" multiple accept=".xlsx" aria-label="Archivos Excel para unir" className="sr-only" disabled={busy}
      onChange={event => { addFiles(Array.from(event.target.files ?? [])); event.target.value = '' }} />
    <div className="flex flex-wrap items-center gap-3">
      <button type="button" disabled={busy} onClick={() => input.current?.click()} className="inline-flex items-center gap-2 rounded-lg border border-navy/20 px-4 py-2 text-sm text-navy disabled:opacity-50"><Plus className="h-4 w-4" />Agregar Excel</button>
      <span className="text-xs text-navy/60">{files.length} de 10 archivos · Hasta 15 MB en total</span>
    </div>
    <ul className="my-5 divide-y divide-navy/10" aria-label="Archivos seleccionados">
      {files.map((file, index) => <li key={`${index}-${file.name}`} className="flex min-w-0 items-center gap-3 py-3">
        <FileSpreadsheet className="h-5 w-5 shrink-0 text-teal" />
        <span className="min-w-0 flex-1 break-words text-sm text-navy">{file.name}</span>
        <button type="button" disabled={busy} title={`Quitar ${file.name}`} aria-label={`Quitar ${file.name}`} className="shrink-0 rounded p-2 text-navy/60 hover:bg-navy/5 disabled:opacity-50" onClick={() => { setFiles(files.filter((_, i) => i !== index)); setDone(false) }}><X className="h-4 w-4" /></button>
      </li>)}
    </ul>
    {error && <p role="alert" className="mb-4 break-words text-sm text-red-700">{error}</p>}
    {busy ? <AnalysisLoadingPanel compact operation="Uniendo las hojas" detail="Comprobando los resultados guardados y preparando el Excel." onCancel={() => request.current?.abort()} />
      : <button type="button" disabled={files.length < 2} onClick={() => void download()} className="inline-flex items-center gap-2 rounded-lg bg-teal px-4 py-3 text-sm font-semibold text-white disabled:opacity-40"><Download className="h-4 w-4" />Unir y descargar</button>}
    {done && <p role="status" className="mt-3 text-sm text-teal">Excel generado. La descarga está lista en tu navegador.</p>}
  </section>
}
