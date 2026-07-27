import { useLayoutEffect, useRef, useState } from 'react'

/** Valor destacado de una tarjeta KPI.
 *
 * Un monto largo ($1.113.784.643) no cabe en una tarjeta angosta y con
 * `break-words` se partía A MITAD DEL NÚMERO ("$1.113.784.6" + "43" en la
 * línea siguiente), que se lee como si fueran dos cifras distintas.
 *
 * Aquí el número NUNCA se parte (`whitespace-nowrap`, garantía estructural) y
 * se muestra tan grande COMO QUEPA: se mide el ancho real del texto y el del
 * contenedor, y se usa el mayor tamaño que entra en una línea. Al depender de
 * la medición y no del archivo, sirve para cualquier Excel.
 */

/** Tamaño inicial estimado por largo del texto: evita el parpadeo de una
 * cifra enorme antes de la primera medición. La medición real lo ajusta. */
export function kpiFontSize(length: number, maxPx: number): number {
  const scale =
    length <= 10 ? 1
      : length <= 13 ? 0.86
        : length <= 16 ? 0.74
          : length <= 20 ? 0.63
            : 0.55
  return Math.max(Math.round(maxPx * scale), 13)
}

const MIN_PX = 12

/** Ancho del texto en píxeles para una tipografía dada. Se mide en un canvas
 * (no en el DOM) para no provocar reflows ni parpadeos al ajustar. */
let measuringContext: CanvasRenderingContext2D | null = null

function measureTextWidth(text: string, fontPx: number, fontFamily: string): number {
  if (!measuringContext) {
    measuringContext = document.createElement('canvas').getContext('2d')
  }
  if (!measuringContext) return 0
  measuringContext.font = `700 ${fontPx}px ${fontFamily}`
  return measuringContext.measureText(text).width
}

export default function KpiValue({
  value,
  maxPx = 22,
  className = '',
}: {
  value: string
  /** Tamaño máximo: nunca crece más que esto aunque sobre espacio. */
  maxPx?: number
  className?: string
}) {
  const text = String(value)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [fontPx, setFontPx] = useState(() => kpiFontSize(text.length, maxPx))

  useLayoutEffect(() => {
    const wrap = wrapRef.current
    if (!wrap) return
    // Se observa el CONTENEDOR, no el texto: cambiar el tamaño de letra altera
    // el alto del texto y observarlo a él realimentaría el bucle.
    let lastWidth = -1
    const fit = () => {
      const available = wrap.clientWidth
      if (!available) return
      const family = getComputedStyle(wrap).fontFamily
      const widthAtMax = measureTextWidth(text, maxPx, family)
      if (widthAtMax <= 0) return
      // El ancho crece de forma lineal con el tamaño, así que basta medir una
      // vez y escalar. Se descuenta 1px para no rozar el borde por redondeo.
      const next = widthAtMax <= available
        ? maxPx
        : Math.max(Math.floor(maxPx * ((available - 1) / widthAtMax)), MIN_PX)
      setFontPx(next)
    }
    fit()
    const observer = new ResizeObserver((entries) => {
      const width = Math.round(entries[0].contentRect.width)
      if (width === lastWidth) return
      lastWidth = width
      fit()
    })
    observer.observe(wrap)
    return () => observer.disconnect()
  }, [text, maxPx])

  return (
    <div ref={wrapRef} className={`min-w-0 ${className}`}>
      <p
        title={text}
        className="overflow-hidden text-ellipsis whitespace-nowrap text-center font-bold leading-tight text-navy"
        style={{ fontSize: `${fontPx}px` }}
      >
        {text}
      </p>
    </div>
  )
}
