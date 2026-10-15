import { expect, test } from '@playwright/test'

test('A failed lazy view keeps navigation usable and reloads only on request', async ({ page }) => {
  await page.goto('/')
  await page.route('**/src/pages/Explorar.tsx*', route => route.abort(), { times: 1 })
  await page.getByRole('link', { name: 'Explorar datos', exact: true }).first().click()
  const alert = page.getByRole('alert')
  await expect(alert.getByRole('heading', { name: 'La interfaz necesita volver a cargarse' })).toBeVisible()
  await expect(alert).toContainText('los cambios pendientes pueden perderse')
  await expect(page.getByRole('link', { name: 'Resumen', exact: true }).first()).toBeVisible()
  await alert.getByRole('button', { name: 'Recargar pagina' }).click()
  await expect(page.getByRole('heading', { name: 'Explorar datos', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'La interfaz necesita volver a cargarse' })).toHaveCount(0)
})
