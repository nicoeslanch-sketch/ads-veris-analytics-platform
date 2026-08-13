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

const PORTABLE_MARK_SELECTOR = [
  '.recharts-bar-rectangle .recharts-rectangle',
  '.recharts-line-dots .recharts-dot',
  '.recharts-area-dots .recharts-dot',
  '.recharts-pie-sector .recharts-sector',
  '.recharts-scatter-symbol',
  '.recharts-radar-dot .recharts-dot',
].join(',')

function nextPaint(): Promise<void> {
  return new Promise((resolve) => window.requestAnimationFrame(() => resolve()))
}

function visibleTooltipText(wrapper: Element): string | null {
  const tooltip = wrapper.querySelector<HTMLElement>('.recharts-tooltip-wrapper')
  if (!tooltip || tooltip.style.visibility === 'hidden') return null
  const rows = Array.from(tooltip.querySelectorAll<HTMLElement>('p,li'))
    .map((row) => row.innerText.trim())
    .filter(Boolean)
  const text = (rows.length > 0 ? rows.join('\n') : tooltip.innerText)
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  return text || null
}

async function collectPortableTooltips(surface: HTMLElement): Promise<Map<string, string>> {
  const result = new Map<string, string>()
  const charts = Array.from(surface.querySelectorAll<HTMLElement>('.recharts-wrapper'))
  for (const [chartIndex, wrapper] of charts.entries()) {
    const marks = Array.from(wrapper.querySelectorAll<SVGElement>(PORTABLE_MARK_SELECTOR))
    for (const [markIndex, mark] of marks.entries()) {
      const box = mark.getBoundingClientRect()
      if (box.width <= 0 || box.height <= 0) continue
      const eventInit: MouseEventInit = {
        bubbles: true,
        clientX: box.left + box.width / 2,
        clientY: box.top + box.height / 2,
      }
      if (typeof PointerEvent !== 'undefined') wrapper.dispatchEvent(new PointerEvent('pointermove', eventInit))
      wrapper.dispatchEvent(new MouseEvent('mousemove', eventInit))
      await nextPaint()
      const text = visibleTooltipText(wrapper)
      if (text) result.set(`${chartIndex}:${markIndex}`, text)
    }
    wrapper.dispatchEvent(new MouseEvent('mouseleave', { bubbles: true }))
  }
  return result
}

async function portableDashboardHtml(surface: HTMLElement, title: string): Promise<string> {
  const tooltipValues = await collectPortableTooltips(surface)
  const clone = surface.cloneNode(true) as HTMLElement
  clone.querySelectorAll('[data-dashboard-actions]').forEach((node) => node.remove())
  clone.querySelectorAll('[data-dashboard-card]').forEach((node) => {
    node.setAttribute('data-portable-card', 'true')
  })
  clone.querySelectorAll<HTMLElement>('.recharts-wrapper').forEach((wrapper, chartIndex) => {
    wrapper.querySelectorAll<SVGElement>(PORTABLE_MARK_SELECTOR).forEach((mark, markIndex) => {
      const tooltip = tooltipValues.get(`${chartIndex}:${markIndex}`)
      if (!tooltip) return
      mark.setAttribute('data-portable-tooltip', tooltip)
      mark.setAttribute('tabindex', '0')
      mark.setAttribute('role', 'button')
      mark.setAttribute('aria-label', tooltip.replace(/\n/g, '. '))
    })
    wrapper.querySelectorAll('.recharts-tooltip-wrapper').forEach((node) => node.remove())
  })
  const escapedTitle = title.replace(/[<>&"]/g, (character) => ({
    '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;',
  })[character] ?? character)
  return `<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapedTitle}</title><style>${embeddedStyles()}
body{margin:0;padding:24px;background:#f7f9fa;color:#1a3a52;font-family:Poppins,Arial,sans-serif}
.portable-shell{max-width:1500px;margin:auto}.portable-note{margin:0 0 16px;padding:12px 16px;border:1px solid #1a3a521a;border-radius:12px;background:white;font-size:12px;color:#1a3a5299}
[data-portable-card]{break-inside:avoid}
[data-portable-tooltip]{cursor:help;outline:none;transition:filter .12s ease,stroke-width .12s ease}
[data-portable-tooltip]:hover,[data-portable-tooltip]:focus,.portable-mark-active{filter:brightness(.9);stroke:#16394f!important;stroke-width:2px!important}
.portable-tooltip{position:fixed;z-index:50;display:none;max-width:min(320px,calc(100vw - 24px));white-space:pre-line;pointer-events:none;border:1px solid #16394f26;border-radius:10px;background:#fff;padding:9px 11px;color:#16394f;font-size:12px;line-height:1.45;box-shadow:0 12px 32px #12283a2b}
.portable-tooltip.is-visible{display:block}
@media(max-width:700px){body{padding:10px}.portable-note{font-size:11px}.portable-tooltip{font-size:13px}}
</style></head><body><main class="portable-shell"><p class="portable-note"><strong>${escapedTitle}</strong> · Copia interactiva generada desde ADS Veris. Pasa el mouse sobre un dato del gráfico o tócalo en el celular para ver su valor. Toca nuevamente o presiona Esc para cerrar el detalle.</p>${clone.outerHTML}</main><div class="portable-tooltip" role="status" aria-live="polite"></div>
<script>(function(){var tip=document.querySelector('.portable-tooltip');var pinned=null;function place(event,mark){var box=mark.getBoundingClientRect();var x=event&&typeof event.clientX==='number'&&event.clientX?event.clientX:box.left+box.width/2;var y=event&&typeof event.clientY==='number'&&event.clientY?event.clientY:box.top;tip.style.left=Math.min(Math.max(12,x+14),window.innerWidth-tip.offsetWidth-12)+'px';tip.style.top=Math.min(Math.max(12,y-tip.offsetHeight-12),window.innerHeight-tip.offsetHeight-12)+'px'}function show(mark,event,pin){if(!mark||!mark.dataset.portableTooltip)return;if(pinned&&pinned!==mark)pinned.classList.remove('portable-mark-active');tip.textContent=mark.dataset.portableTooltip;tip.classList.add('is-visible');mark.classList.add('portable-mark-active');if(pin)pinned=mark;requestAnimationFrame(function(){place(event,mark)})}function hide(mark,force){if(pinned&&!force)return;if(mark)mark.classList.remove('portable-mark-active');if(force&&pinned){pinned.classList.remove('portable-mark-active');pinned=null}tip.classList.remove('is-visible')}document.addEventListener('pointerover',function(event){var mark=event.target.closest('[data-portable-tooltip]');if(mark&&!pinned)show(mark,event,false)});document.addEventListener('pointermove',function(event){var mark=event.target.closest('[data-portable-tooltip]');if(mark&&!pinned)place(event,mark)});document.addEventListener('pointerout',function(event){var mark=event.target.closest('[data-portable-tooltip]');if(mark&&!pinned)hide(mark,false)});document.addEventListener('click',function(event){var mark=event.target.closest('[data-portable-tooltip]');if(!mark){hide(null,true);return}event.preventDefault();event.stopPropagation();if(pinned===mark){hide(mark,true)}else{show(mark,event,true)}});document.addEventListener('focusin',function(event){var mark=event.target.closest('[data-portable-tooltip]');if(mark)show(mark,null,false)});document.addEventListener('focusout',function(event){var mark=event.target.closest('[data-portable-tooltip]');if(mark&&!pinned)hide(mark,false)});document.addEventListener('keydown',function(event){if(event.key==='Escape')hide(null,true);if((event.key==='Enter'||event.key===' ')&&event.target.matches('[data-portable-tooltip]')){event.preventDefault();event.target.click()}})})();</script></body></html>`
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

  const exportHtml = async () => {
    if (!surfaceRef.current) return
    setExporting('dashboard-html')
    setError(null)
    try {
      const html = await portableDashboardHtml(surfaceRef.current, title)
      const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
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
            <button type="button" onClick={() => void exportHtml()} disabled={exporting !== null} className="dashboard-toolbar-button">
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
