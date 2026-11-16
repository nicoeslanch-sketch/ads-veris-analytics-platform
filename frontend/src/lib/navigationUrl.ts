/** API-provided links still need a browser-side protocol boundary. */
export function safeHttpsUrl(value: unknown, origin?: string): string | undefined {
  if (typeof value !== 'string' || /[\u0000-\u001f\u007f\\]/.test(value)) return undefined
  try {
    const url = new URL(value)
    if (url.protocol !== 'https:' || url.username || url.password) return undefined
    if (origin && url.origin !== origin) return undefined
    return url.href
  } catch {
    return undefined
  }
}
