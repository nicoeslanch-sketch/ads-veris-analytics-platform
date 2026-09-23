import { expect, test } from '@playwright/test'

for (const width of [320, 390, 1280]) {
  test(`admin monitoring is lazy, handles failure, and fits at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    let requests = 0
    let fail = false
    await page.route('**/admin/operations', route => {
      requests++
      return fail ? route.fulfill({ status: 503, json: { detail: 'Unavailable' } }) : route.fulfill({ json: {
        sampled_at: '2026-09-23T09:00:00Z',
        http: { instances: 1, requests: 12345678, errors: 12, limited: 30, slow: 100 },
        queue: { queued: 27, running: 1, max_active: 32, oldest_wait_seconds: 999 },
        storage: { used_bytes: 98765432100000, reserved_bytes: 1000, limit_bytes: 100000000000000 },
        alerts: [{ code: 'QUEUE_WAIT', severity: 'warning', title: 'Archivos esperando', detail: 'Revisa la actividad del worker.' }],
      } })
    })
    await page.goto('/e2e/fixtures/operations.html')
    await expect(page.getByRole('button', { name: 'Estado operativo' })).toBeVisible()
    expect(requests).toBe(0)
    await page.getByRole('button', { name: 'Estado operativo' }).click()
    await expect(page.getByText('Archivos esperando', { exact: true })).toBeVisible()
    expect(requests).toBe(1)
    const overflow = await page.getByRole('region', { name: 'Estado operativo', exact: true }).evaluate(root => [root, ...root.querySelectorAll('p, dt, dd, button')]
      .filter(node => node.scrollWidth > node.clientWidth + 1).map(node => node.tagName))
    expect(overflow).toEqual([])
    await page.screenshot({ path: testInfo.outputPath(`operations-${width}.png`), fullPage: true })
    fail = true
    await page.getByRole('button', { name: 'Actualizar estado operativo' }).click()
    await expect(page.getByRole('alert')).toContainText('No se pudo verificar')
    await expect(page.getByText('Archivos esperando', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Sin alertas', { exact: false })).toHaveCount(0)
  })
}
