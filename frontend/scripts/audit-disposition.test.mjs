import { test } from 'node:test'
import assert from 'node:assert/strict'
import { developmentGlobDisposition as accepted } from './audit-disposition.mjs'
import { isCompleteAudit } from './audit-report.mjs'

test('registry and incomplete responses cannot satisfy the dependency check', () => {
  const clean = {auditReportVersion: 2, vulnerabilities: {}, metadata: {vulnerabilities: {total: 0}}}
  assert.equal(isCompleteAudit(clean, 0), true)
  assert.equal(isCompleteAudit(clean, 1), false)
  for (const response of [null, {}, {error: {code: 'E503'}}, {...clean, error: {}},
    {...clean, vulnerabilities: []}, {...clean, metadata: {}}]) {
    assert.equal(isCompleteAudit(response, 0), false)
  }
  const flagged = {...clean, vulnerabilities: {pkg: {severity: 'high', via: ['dep']}},
    metadata: {vulnerabilities: {total: 1}}}
  assert.equal(isCompleteAudit(flagged, 1), true)
  assert.equal(isCompleteAudit(flagged, null), false)
})

const ids = new Set(['GHSA-fc5q-39xc-vjpf'])
const vulnerability = { nodes: ['node_modules/picomatch'] }
const lock = { packages: { 'node_modules/picomatch': { dev: true } } }
const now = Date.parse('2026-11-18T00:00:00Z')
test('temporary disposition is restricted to reviewed dev dependency paths', () => {
  assert.equal(accepted('picomatch', vulnerability, ids, lock, now), true)
  assert.equal(accepted('picomatch', vulnerability, ids, {packages:{}}, now), false)
  assert.equal(accepted('picomatch', vulnerability, ids,
    { packages: { 'node_modules/picomatch': {dev:false} } }, now), false)
  assert.equal(accepted('unknown', vulnerability, ids, lock, now), false)
  assert.equal(accepted('picomatch', {nodes:[]}, ids, lock, now), false)
})
test('new advisories and expired dispositions always block', () => {
  assert.equal(accepted('picomatch', vulnerability, new Set([...ids, 'GHSA-new']), lock, now), false)
  assert.equal(accepted('picomatch', vulnerability, new Set(), lock, now), false)
  assert.equal(accepted('picomatch', vulnerability, ids, lock, Date.parse('2026-11-25T00:00:00Z')), false)
})
