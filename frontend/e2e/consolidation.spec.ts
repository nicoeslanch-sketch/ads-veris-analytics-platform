import { expect, test } from '@playwright/test'

test('union simple admite varios Excel y descarga un unico archivo', async ({ page }) => {
  await page.route('**/consolidation/workbook', async route => {
    expect(route.request().postDataBuffer()?.toString()).toContain('ventas.xlsx')
    expect(route.request().postDataBuffer()?.toString()).toContain('productos.xlsx')
    await route.fulfill({ status: 200, headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'Content-Disposition': 'attachment; filename="Archivos_unidos.xlsx"' }, body: Buffer.from('test-download') })
  })
  await page.goto('/estandarizacion')
  await page.getByRole('button', { name: /Consolidar archivos/i }).click()
  await expect(page.getByRole('button', { name: 'Unir y descargar' })).toBeDisabled()
  await page.getByLabel('Archivos Excel para unir').setInputFiles([
    { name: 'ventas.xlsx', mimeType: 'application/octet-stream', buffer: Buffer.from('one') },
    { name: 'productos.xlsx', mimeType: 'application/octet-stream', buffer: Buffer.from('two') },
  ])
  await expect(page.getByText('ventas.xlsx', { exact: true })).toBeVisible()
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Unir y descargar' }).click()
  expect((await downloaded).suggestedFilename()).toBe('Archivos_unidos.xlsx')
  await expect(page.getByRole('status')).toContainText('Excel generado')
})

test('pantalla de carga no desborda en tablet ni móvil', async ({ page }) => {
  for (const viewport of [{ width: 768, height: 1024 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport)
    await page.goto('/estandarizacion')
    await page.getByRole('button', { name: /Consolidar archivos/i }).click()
    await expect(page.getByRole('heading', { name: 'Consolidar archivos' })).toBeVisible()
    await page.getByLabel('Archivos Excel para unir').setInputFiles({ name: 'no.csv', mimeType: 'text/csv', buffer: Buffer.from('a,b') })
    await expect(page.getByRole('alert')).toContainText('.xlsx')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: `test-results/workbook-bundle-${viewport.width}.png`, fullPage: true })
  }
})
