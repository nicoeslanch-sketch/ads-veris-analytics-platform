import { spawnSync } from 'node:child_process'

// GHSA-qwww-vcr4-c8h2 only affects unstable RSC APIs. ADS Veris is a Vite SPA
// and does not use React Server Components. Keep every other high/critical
// advisory blocking while npm has not published the indicated patched release.
const acceptedAdvisories = new Set(['GHSA-qwww-vcr4-c8h2'])
const command = process.platform === 'win32' ? process.env.ComSpec ?? 'cmd.exe' : 'npm'
const args =
  process.platform === 'win32'
    ? ['/d', '/s', '/c', 'npm audit --json']
    : ['audit', '--json']
const audit = spawnSync(command, args, {
  encoding: 'utf8',
})

if (!audit.stdout) {
  process.stderr.write(audit.stderr || 'npm audit no entregó un resultado.\n')
  process.exit(1)
}

let report
try {
  report = JSON.parse(audit.stdout)
} catch {
  process.stderr.write(audit.stdout)
  process.stderr.write(audit.stderr || '')
  process.exit(1)
}

const vulnerabilities = report.vulnerabilities ?? {}

function advisoryIds(name, visited = new Set()) {
  if (visited.has(name)) return new Set()
  visited.add(name)
  const vulnerability = vulnerabilities[name]
  const ids = new Set()
  for (const source of vulnerability?.via ?? []) {
    if (typeof source === 'string') {
      for (const id of advisoryIds(source, visited)) ids.add(id)
      continue
    }
    const match = String(source.url ?? '').match(/(GHSA-[a-z0-9-]+)$/i)
    if (match) ids.add(match[1])
  }
  return ids
}

const blocked = []
const accepted = []
for (const [name, vulnerability] of Object.entries(vulnerabilities)) {
  if (!['high', 'critical'].includes(vulnerability.severity)) continue
  const ids = advisoryIds(name)
  if (ids.size > 0 && [...ids].every((id) => acceptedAdvisories.has(id))) {
    accepted.push(`${name}: ${[...ids].join(', ')}`)
  } else {
    blocked.push(`${name}: ${[...ids].join(', ') || 'sin identificador GHSA'}`)
  }
}

if (accepted.length) {
  process.stdout.write(
    `Aviso aceptado por no aplicar al frontend SPA:\n- ${accepted.join('\n- ')}\n`,
  )
}
if (blocked.length) {
  process.stderr.write(
    `Vulnerabilidades high/critical que bloquean el CI:\n- ${blocked.join('\n- ')}\n`,
  )
  process.exit(1)
}

process.stdout.write('Sin vulnerabilidades high/critical aplicables.\n')
