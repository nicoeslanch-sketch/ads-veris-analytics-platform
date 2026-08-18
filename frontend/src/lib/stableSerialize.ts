function normalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalize)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, nested]) => [key, normalize(nested)]),
    )
  }
  return value
}

/** Serialización determinística para que restaurar el mismo JSON con otro
 * orden de propiedades no cree una caché distinta. El orden de arrays sí se
 * conserva porque puede representar precedencia o selección del usuario. */
export function stableSerialize(value: unknown): string {
  return JSON.stringify(normalize(value))
}

