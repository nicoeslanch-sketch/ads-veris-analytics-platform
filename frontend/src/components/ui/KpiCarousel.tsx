import {
  Children,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

/** Fila ÚNICA deslizable de tarjetas.
 *
 * Decenas de KPIs apilados en una grilla empujaban el resto del tablero varias
 * pantallas hacia abajo. Aquí el bloque ocupa una sola fila: se ven las
 * primeras (las más relevantes) y el resto se recorre con las flechas, la
 * rueda del mouse o arrastrando. Las flechas solo aparecen si hay algo más
 * que mostrar, así que con pocas tarjetas se comporta como una fila normal.
 */
export default function KpiCarousel({
  children,
  itemWidth = 252,
  label,
}: {
  children: ReactNode
  /** Ancho fijo de cada tarjeta: mantiene la fila pareja y predecible. */
  itemWidth?: number
  label: string
}) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [atStart, setAtStart] = useState(true)
  const [atEnd, setAtEnd] = useState(true)

  const sync = useCallback(() => {
    const track = trackRef.current
    if (!track) return
    const max = track.scrollWidth - track.clientWidth
    // 2px de tolerancia: el scroll fraccionario de algunos zooms nunca llega
    // exacto al extremo y dejaba una flecha activa sin nada que recorrer.
    setAtStart(track.scrollLeft <= 2)
    setAtEnd(track.scrollLeft >= max - 2)
  }, [])

  useEffect(() => {
    const track = trackRef.current
    if (!track) return
    sync()
    // El ancho disponible cambia al abrir el panel de IA o el sidebar, no solo
    // al redimensionar la ventana: se observa el elemento, no el viewport.
    const observer = new ResizeObserver(sync)
    observer.observe(track)
    return () => observer.disconnect()
  }, [sync, children])

  const scrollByPage = (direction: 1 | -1) => {
    const track = trackRef.current
    if (!track) return
    track.scrollBy({
      left: direction * Math.max(track.clientWidth * 0.85, itemWidth),
      behavior: 'smooth',
    })
  }

  const items = Children.toArray(children)
  const scrollable = !(atStart && atEnd)

  return (
    <div className="relative" role="group" aria-label={label}>
      <div
        ref={trackRef}
        onScroll={sync}
        className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {items.map((item, index) => (
          <div
            key={index}
            className="shrink-0 snap-start"
            style={{ width: itemWidth }}
          >
            {item}
          </div>
        ))}
      </div>

      {scrollable && (
        <>
          <CarouselButton
            side="left"
            disabled={atStart}
            onClick={() => scrollByPage(-1)}
          />
          <CarouselButton
            side="right"
            disabled={atEnd}
            onClick={() => scrollByPage(1)}
          />
        </>
      )}
    </div>
  )
}

function CarouselButton({
  side,
  disabled,
  onClick,
}: {
  side: 'left' | 'right'
  disabled: boolean
  onClick: () => void
}) {
  const Icon = side === 'left' ? ChevronLeft : ChevronRight
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={side === 'left' ? 'Ver anteriores' : 'Ver siguientes'}
      className={[
        'absolute top-1/2 z-10 flex h-8 w-8 -translate-y-1/2 items-center justify-center',
        'rounded-full border border-navy/10 bg-white text-navy shadow-md transition',
        'hover:border-teal/50 hover:text-teal',
        'disabled:pointer-events-none disabled:opacity-0',
        side === 'left' ? '-left-3' : '-right-3',
      ].join(' ')}
    >
      <Icon className="h-4 w-4" />
    </button>
  )
}
