// Temporary reachability disposition, not a claim that the dependency is patched.
export function developmentGlobDisposition(name, vulnerability, ids, lock, now = Date.now()) {
  const reviewed = new Set(['picomatch', 'fdir', 'tinyglobby', 'vite', 'vitest'])
  if (!reviewed.has(name) || ids.size !== 1 || !ids.has('GHSA-fc5q-39xc-vjpf')) return false
  if (now >= Date.parse('2026-11-25T00:00:00Z')) return false
  const nodes = vulnerability.nodes
  return Array.isArray(nodes) && nodes.length > 0 && nodes.every(path => {
    const entry = lock.packages?.[path]
    return entry?.dev === true
      && (path.endsWith(`/node_modules/${name}`) || path === `node_modules/${name}`)
  })
}
