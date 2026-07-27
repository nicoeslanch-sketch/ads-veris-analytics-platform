/** Valor destacado de una tarjeta KPI.
 *
 * Un monto largo ($1.113.784.643) no cabe en una tarjeta angosta y con
 * `break-words` se partía A MITAD DEL NÚMERO ("$1.113.784.6" + "43" en la
 * línea siguiente), que se lee como si fueran dos cifras distintas.
 *
 * Aquí el número NUNCA se parte: se reduce el tamaño de letra según su largo
 * — que es lo que hace un tablero real — y, en el caso extremo, se recorta
 * con "…" conservando el valor completo en el tooltip. Como el ajuste depende
 * del largo del texto y no del archivo, sirve para cualquier Excel: montos de
 * miles o de miles de millones caben igual.
 */
/** Tamaño de letra (px) para que un valor de `length` caracteres quepa en una
 * tarjeta angosta. Un dígito en negrita ocupa ~0,6em, así que estos tramos
 * mantienen el valor dentro de ~160px útiles. Nunca baja de 13px. */
export function kpiFontSize(length: number, maxPx: number): number {
  const scale =
    length <= 10 ? 1
      : length <= 13 ? 0.86
        : length <= 16 ? 0.74
          : length <= 20 ? 0.63
            : 0.55
  return Math.max(Math.round(maxPx * scale), 13)
}

export default function KpiValue({
  value,
  maxPx = 22,
  className = '',
}: {
  value: string
  /** Tamaño ideal cuando el valor es corto; se reduce si no cabría. */
  maxPx?: number
  className?: string
}) {
  const text = String(value)
  return (
    <p
      title={text}
      className={`overflow-hidden text-ellipsis whitespace-nowrap font-bold leading-tight text-navy ${className}`}
      style={{ fontSize: `${kpiFontSize(text.length, maxPx)}px` }}
    >
      {text}
    </p>
  )
}
