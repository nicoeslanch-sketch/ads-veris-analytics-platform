import { expect, test } from '@playwright/test'

test('asistente unificado muestra cuatro pasos y admite varios archivos', async ({ page }) => {
  await page.goto('/estandarizacion')
  await page.getByRole('button', { name: /Consolidar y recodificar archivos/i }).click()

  const steps = page.getByRole('list', { name: 'Pasos de consolidación' }).getByRole('button')
  await expect(steps).toHaveCount(4)
  await expect(steps.nth(0)).toContainText('Cargar')
  await expect(steps.nth(1)).toContainText('Revisar')
  await expect(steps.nth(2)).toContainText('Comprobar')
  await expect(steps.nth(3)).toContainText('Obtener resultado')

  await page.locator('input[type="file"]').setInputFiles([
    { name: 'ventas.csv', mimeType: 'text/csv', buffer: Buffer.from('ID,MONTO\n1,10') },
    { name: 'productos.csv', mimeType: 'text/csv', buffer: Buffer.from('ID,NOMBRE\n1,Uno') },
  ])
  await expect(page.getByText('ventas.csv')).toBeVisible()
  await expect(page.getByText('productos.csv')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reintentar' })).toHaveCount(2)
})

test('pantalla de carga no desborda en tablet ni móvil', async ({ page }) => {
  for (const viewport of [{ width: 768, height: 1024 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport)
    await page.goto('/estandarizacion')
    await page.getByRole('button', { name: /Consolidar y recodificar archivos/i }).click()
    await expect(page.getByRole('heading', { name: 'Consolidar y recodificar archivos' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
})
