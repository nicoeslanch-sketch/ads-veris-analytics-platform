import { expect, test } from '@playwright/test'

test('Vite denies protected files even with raw and import queries', async ({ request }) => {
  for (const query of ['', '?raw', '?import&raw', '?import&url&inline']) {
    const response = await request.get(`/e2e/fixtures/denied.crt${query}`)
    expect([403, 404]).toContain(response.status())
    expect(await response.text()).not.toContain('ADS_VERIS_SYNTHETIC_DENY_PROBE_NOT_A_CERTIFICATE')
  }
})
