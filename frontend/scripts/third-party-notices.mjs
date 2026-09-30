import { readFile, readdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

// Generate distribution notices from the exact installed production lockfile.
const root = resolve(import.meta.dirname, '..')
const lock = JSON.parse(await readFile(resolve(root, 'package-lock.json'), 'utf8'))
const notices = ['ADS Veris: third-party notices. Licenses apply to the named components, not to ADS Veris proprietary code.']
for (const [path, entry] of Object.entries(lock.packages)) {
  if (!path || entry.dev) continue
  const dir = resolve(root, path)
  const manifest = JSON.parse(await readFile(resolve(dir, 'package.json'), 'utf8'))
  const files = (await readdir(dir)).filter(name => /^(license|licence|copying|notice)(\..*)?$/i.test(name))
  const victory = manifest.name === 'victory-vendor' && manifest.version === '37.3.6'
  if (!files.length && !victory) throw new Error(`Missing license notice: ${manifest.name}. Review before distribution.`)
  notices.push(`\n=== ${manifest.name} ${manifest.version} (${manifest.license ?? entry.license ?? 'see below'}) ===`)
  for (const file of files.sort()) notices.push(await readFile(resolve(dir, file), 'utf8'))
  if (victory) {
    notices.push(await readFile(resolve(root, 'licenses/victory-vendor-37.3.6.txt'), 'utf8'))
    for (const vendor of (await readdir(resolve(dir, 'lib-vendor'))).sort()) {
      notices.push(`Vendored component: ${vendor}`, await readFile(resolve(dir, 'lib-vendor', vendor, 'LICENSE'), 'utf8'))
    }
  }
}
await writeFile(resolve(root, 'public/THIRD_PARTY_NOTICES.txt'), notices.join('\n'), 'utf8')
console.log('Production dependency license notices generated.')
