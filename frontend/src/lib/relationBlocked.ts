/** Cuando una relación guardada deja de ser válida para el libro actual, el
 * motor rechaza el análisis con un motivo técnico ("La hoja de referencia
 * contiene claves duplicadas."). La página mostraba ese texto con un botón
 * "Reintentar" que JAMÁS podía funcionar: la relación sigue siendo insegura,
 * así que reintentar reproduce el mismo error.
 *
 * Aquí se traduce ese motivo a una explicación de negocio y una salida real:
 * ir a "Relación manual" a cambiarla o quitarla.
 */

export interface RelationBlockedNotice {
  titulo: string
  explicacion: string
  consecuencia: string
}

const MOTIVOS: Array<{ match: RegExp; notice: RelationBlockedNotice }> = [
  {
    match: /claves duplicadas/i,
    notice: {
      titulo: 'La relación elegida uniría mal tus datos',
      explicacion:
        'La hoja que usaste como referencia repite la misma clave en varias filas, así que una venta encontraría más de una coincidencia.',
      consecuencia:
        'Unirlas duplicaría filas e inflaría tus ventas, por eso el análisis se detiene en vez de mostrarte un total equivocado.',
    },
  },
  {
    match: /cobertura de la clave/i,
    notice: {
      titulo: 'La relación elegida cubre muy pocos registros',
      explicacion:
        'La mayoría de las filas no trae la clave que conecta ambas hojas, así que casi nada quedaría relacionado.',
      consecuencia:
        'El resultado se calcularía sobre una parte mínima de tus datos y no representaría tu negocio.',
    },
  },
  {
    match: /solapamiento/i,
    notice: {
      titulo: 'Las hojas elegidas casi no tienen datos en común',
      explicacion:
        'Los valores de la clave de una hoja casi no aparecen en la otra: probablemente no son las columnas que se corresponden.',
      consecuencia:
        'Prácticamente ninguna fila encontraría su par, así que el análisis quedaría vacío.',
    },
  },
  {
    match: /relaci[oó]n no es segura/i,
    notice: {
      titulo: 'La relación elegida no es segura',
      explicacion: 'La conexión entre esas dos hojas no cumple las condiciones para unirlas sin alterar tus cifras.',
      consecuencia: 'El análisis se detiene para no entregarte totales que no cuadran con tu archivo.',
    },
  },
]

/** Devuelve la explicación accionable si el error viene de una relación
 * inválida; `null` si es cualquier otro error (que sí puede reintentarse). */
export function relationBlockedNotice(message: string | null | undefined): RelationBlockedNotice | null {
  if (!message) return null
  return MOTIVOS.find((entry) => entry.match.test(message))?.notice ?? null
}
