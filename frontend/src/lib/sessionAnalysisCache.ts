const CACHE_PREFIX = 'ads-veris:analysis:v1:'
const CACHE_TTL_MS = 24 * 60 * 60 * 1000

export type SessionAnalysisKind = 'metrics' | 'relationships' | 'catalog' | 'dashboard'

interface StoredAnalysis<T> {
  identity: string
  storedAt: number
  value: T
}

function storage(): Storage | null {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage
  } catch {
    return null
  }
}

function hashIdentity(identity: string): string {
  let hash = 2166136261
  for (let index = 0; index < identity.length; index += 1) {
    hash ^= identity.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return `${(hash >>> 0).toString(36)}-${identity.length.toString(36)}`
}

function storageKey(kind: SessionAnalysisKind, identity: string): string {
  return `${CACHE_PREFIX}${kind}:${hashIdentity(identity)}`
}

function cacheKeys(target: Storage, kind?: SessionAnalysisKind): string[] {
  const prefix = kind ? `${CACHE_PREFIX}${kind}:` : CACHE_PREFIX
  const keys: string[] = []
  for (let index = 0; index < target.length; index += 1) {
    const key = target.key(index)
    if (key?.startsWith(prefix)) keys.push(key)
  }
  return keys
}

function removeOldest(target: Storage, kind: SessionAnalysisKind, keep: number) {
  const entries = cacheKeys(target, kind).map((key) => {
    try {
      const parsed = JSON.parse(target.getItem(key) ?? '') as Partial<StoredAnalysis<unknown>>
      return { key, storedAt: Number(parsed.storedAt) || 0 }
    } catch {
      return { key, storedAt: 0 }
    }
  })
  entries
    .sort((left, right) => right.storedAt - left.storedAt)
    .slice(keep)
    .forEach(({ key }) => target.removeItem(key))
}

/**
 * Conserva resultados ya calculados durante la sesión de la pestaña. A
 * diferencia de localStorage, no comparte datos empresariales entre pestañas
 * ni sobrevive al cierre del navegador. Sí sobrevive una recarga o un nuevo
 * despliegue del frontend, que era cuando se perdía el trabajo terminado.
 */
export function readSessionAnalysis<T>(
  kind: SessionAnalysisKind,
  identity: string,
): T | null {
  const target = storage()
  if (!target) return null
  const key = storageKey(kind, identity)
  try {
    const parsed = JSON.parse(target.getItem(key) ?? '') as StoredAnalysis<T>
    if (
      parsed.identity !== identity
      || !Number.isFinite(parsed.storedAt)
      || Date.now() - parsed.storedAt > CACHE_TTL_MS
    ) {
      target.removeItem(key)
      return null
    }
    return parsed.value ?? null
  } catch {
    target.removeItem(key)
    return null
  }
}

export function writeSessionAnalysis<T>(
  kind: SessionAnalysisKind,
  identity: string,
  value: T,
  maxEntries: number,
) {
  const target = storage()
  if (!target) return
  const key = storageKey(kind, identity)
  const serialized = JSON.stringify({ identity, storedAt: Date.now(), value })
  try {
    target.setItem(key, serialized)
    removeOldest(target, kind, maxEntries)
  } catch {
    // Si la cuota de la pestaña está llena, priorizamos la vista actual.
    removeOldest(target, kind, Math.max(0, Math.floor(maxEntries / 2)))
    try {
      target.setItem(key, serialized)
    } catch {
      // La caché es una optimización: un resultado demasiado grande puede
      // seguir usándose en memoria sin bloquear el dashboard.
    }
  }
}

export function clearSessionAnalysis(kinds?: SessionAnalysisKind[]) {
  const target = storage()
  if (!target) return
  const keys = kinds?.length
    ? kinds.flatMap((kind) => cacheKeys(target, kind))
    : cacheKeys(target)
  for (const key of new Set(keys)) target.removeItem(key)
}

