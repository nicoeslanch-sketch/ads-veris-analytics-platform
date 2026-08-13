import { Download, Expand, ImageDown, Loader2, Maximize2, X } from 'lucide-react'
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import { toPng } from 'html-to-image'

type ExportKind = 'chart' | 'dashboard-image' | 'dashboard-html' | null

function safeFileName(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase() || 'dashboard'
}

function downloadUrl(url: string, fileName: string) {
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

function embeddedStyles(): string {
  return Array.from(document.styleSheets).map((sheet) => {
    try {
      return Array.from(sheet.cssRules).map((rule) => rule.cssText).join('\n')
    } catch {
      return ''
    }
  }).join('\n')
}

function portableDashboardHtml(surface: HTMLElement, title: string): string {
  const clone = surface.cloneNode(true) as HTMLElement
  clone.querySelectorAll('[data-dashboard-actions]').forEach((node) => node.remove())
  clone.querySelectorAll('[data-dashboard-card]').forEach((node) => {
    node.setAttribute('data-portable-card', 'true')
    node.setAttribute('tabindex', '0')
    node.setAttribute('title', 'Haz clic para ampliar esta tarjeta')
  })
  const escapedTitle = title.replace(/[<>&"]/g, (character) => ({
    '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;',
  })[character] ?? character)
  return `<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapedTitle}</title><style>${embeddedStyles()}
body{margin:0;padding:24px;background:#f7f9fa;color:#1a3a52;font-family:Poppins,Arial,sans-serif}
.portable-shell{max-width:1500px;margin:auto}.portable-note{margin:0 0 16px;padding:12px 16px;border:1px solid #1a3a521a;border-radius:12px;background:white;font-size:12px;color:#1a3a5299}
[data-portable-card]{cursor:zoom-in;transition:box-shadow .2s,transform .2s}[data-portable-card]:hover{box-shadow:0 14px 34px #12283a1f;transform:translateY(-1px)}
[data-portable-card].portable-expanded{position:fixed!important;inset:3vh 3vw;z-index:10;overflow:auto;background:white;cursor:zoom-out;box-shadow:0 30px 80px #12283a55}
.portable-backdrop{position:fixed;inset:0;background:#12283acc;z-index:9}
@media(max-width:700px){body{padding:10px}[data-portable-card].portable-expanded{inset:1vh 2vw}}
</style></head><body><main class="portable-shell"><p class="portable-note"><strong>${escapedTitle}</strong> · Copia navegable generada desde ADS Veris. Haz clic en una tarjeta para ampliarla. Los filtros y tooltips dinámicos permanecen disponibles en la plataforma.</p>${clone.outerHTML}</main>
<script>document.addEventListener('click',function(event){var card=event.target.closest('[data-portable-card]');if(!card)return;var expanded=card.classList.toggle('portable-expanded');var old=document.querySelector('.portable-backdrop');if(old)old.remove();if(expanded){var back=document.createElement('div');back.className='portable-backdrop';back.onclick=function(){card.classList.remove('portable-expanded');back.remove()};document.body.appendChild(back)}});document.addEventListener('keydown',function(event){if(event.key==='Escape'){document.querySelectorAll('.portable-expanded').forEach(function(node){node.classList.remove('portable-expanded')});var back=document.querySelector('.portable-backdrop');if(back)back.remove()}})</script></body></html>`
}

function chartTitle(card: HTMLElement, fallback: string): string {
  return card.querySelector('h2,h3,h4')?.textContent?.trim() || fallback
}

export default function DashboardExperience({
  title,
  enabled = true,
  children,
}: {
  title: string
  enabled?: boolean
  children: ReactNode
}) {
  const surfaceRef = useRef<HTMLDivElement>(null)
  const [chartCards, setChartCards] = useState<HTMLElement[]>([])
  const [expandedCard, setExpandedCard] = useState<HTMLElement | null>(null)
  const [fullScreen, setFullScreen] = useState(false)
  const [exporting, setExporting] = useState<ExportKind>(null)
  const [error, setError] = useState<string | null>(null)
  const fileStem = useMemo(() => safeFileName(title), [title])

  useEffect(() => {
    if (!enabled || !surfaceRef.current) return
    const surface = surfaceRef.current
    const discover = () => {
      const found = Array.from(surface.querySelectorAll(
        '.recharts-responsive-container, [data-chart-kind], [data-dashboard-visual]',
      )).map((node) => node.closest('[data-dashboard-card]'))
        .filter((node): node is HTMLElement => node instanceof HTMLElement)
        .filter((node, index, all) => all.indexOf(node) === index)
      setChartCards((current) => (
        current.length === found.length && current.every((node, index) => node === found[index])
          ? current
          : found
      ))
    }
    discover()
    const observer = new MutationObserver(discover)
    observer.observe(surface, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [enabled, children])

  useEffect(() => {
    chartCards.forEach((card) => card.classList.add('dashboard-enhanced-card'))
    return () => chartCards.forEach((card) => card.classList.remove('dashboard-enhanced-card'))
  }, [chartCards])

  useEffect(() => {
    if (!expandedCard && !fullScreen) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const close = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      expandedCard?.classList.remove('dashboard-card-expanded')
      setExpandedCard(null)
      setFullScreen(false)
    }
    window.addEventListener('keydown', close)
    return () => {
      document.body.style.overflow = previous
      window.removeEventListener('keydown', close)
    }
  }, [expandedCard, fullScreen])

  const closeCard = () => {
    expandedCard?.classList.remove('dashboard-card-expanded')
    setExpandedCard(null)
  }

  const expandCard = (card: HTMLElement) => {
    expandedCard?.classList.remove('dashboard-card-expanded')
    card.classList.add('dashboard-card-expanded')
    setExpandedCard(card)
  }

  const exportPng = async (target: HTMLElement, name: string, kind: ExportKind) => {
    setExporting(kind)
    setError(null)
    try {
      await document.fonts.ready
      const dataUrl = await toPng(target, {
        backgroundColor: '#f7f9fa',
        cacheBust: true,
        pixelRatio: kind === 'chart' ? 2 : 1.25,
        filter: (node) => !(node instanceof HTMLElement && node.hasAttribute('data-dashboard-actions')),
      })
      downloadUrl(dataUrl, `${safeFileName(name)}.png`)
    } catch {
      setError('No pudimos crear la imagen. Prueba la descarga HTML, que admite tableros más extensos.')
    } finally {
      setExporting(null)
    }
  }

  const exportHtml = () => {
    if (!surfaceRef.current) return
    setExporting('dashboard-html')
    setError(null)
    try {
      const blob = new Blob([portableDashboardHtml(surfaceRef.current, title)], { type: 'text/html;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      downloadUrl(url, `${fileStem}.html`)
      window.setTimeout(() => URL.revokeObjectURL(url), 1_000)
    } catch {
      setError('No pudimos preparar la copia HTML del dashboard.')
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className={fullScreen ? 'dashboard-fullscreen-shell' : ''}>
      {enabled && (
        <div
          className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-navy/10 bg-white px-3 py-2.5 shadow-sm"
          data-dashboard-actions
        >
          <div className="min-w-0">
            <p className="text-xs font-semibold text-navy">{title}</p>
            <p className="text-[10px] text-navy/45">Amplía gráficos o exporta el tablero visible.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => setFullScreen((value) => !value)} className="dashboard-toolbar-button">
              {fullScreen ? <X className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
              {fullScreen ? 'Cerrar vista' : 'Ver dashboard completo'}
            </button>
            <button type="button" onClick={exportHtml} disabled={exporting !== null} className="dashboard-toolbar-button">
              {exporting === 'dashboard-html' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
              Descargar HTML
            </button>
            <button
              type="button"
              onClick={() => surfaceRef.current && void exportPng(surfaceRef.current, title, 'dashboard-image')}
              disabled={exporting !== null}
              className="dashboard-toolbar-button"
            >
              {exporting === 'dashboard-image' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImageDown className="h-3.5 w-3.5" />}
              Descargar imagen
            </button>
          </div>
        </div>
      )}
      {error && <p className="mb-4 rounded-lg border border-coral/30 bg-coral/[0.07] px-3 py-2 text-xs text-coral">{error}</p>}
      <div ref={surfaceRef} className="dashboard-export-surface" data-dashboard-surface>
        {children}
      </div>

      {chartCards.map((card) => createPortal(
        <div key="actions" className="dashboard-card-actions" data-dashboard-actions>
          <button type="button" onClick={() => expandCard(card)} aria-label="Ampliar gráfico" title={`Ampliar ${chartTitle(card, 'gráfico')}`}>
            <Expand className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => void exportPng(card, chartTitle(card, 'grafico'), 'chart')}
            aria-label="Descargar gráfico"
            title={`Descargar ${chartTitle(card, 'gráfico')} como PNG`}
            disabled={exporting !== null}
          >
            {exporting === 'chart' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
          </button>
        </div>,
        card,
      ))}

      {(expandedCard || fullScreen) && createPortal(
        <button
          type="button"
          className="dashboard-modal-backdrop"
          aria-label="Cerrar vista ampliada"
          onClick={() => {
            closeCard()
            setFullScreen(false)
          }}
        />,
        document.body,
      )}
      {expandedCard && createPortal(
        <button type="button" className="dashboard-expanded-close" onClick={closeCard} aria-label="Cerrar gráfico ampliado">
          <X className="h-4 w-4" /> Cerrar
        </button>,
        document.body,
      )}
    </div>
  )
}

export { safeFileName }
