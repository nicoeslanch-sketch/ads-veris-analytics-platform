import { expect, test } from '@playwright/test'

test('consolidación permanece oculta con el feature flag apagado', async ({ page }) => {
  await page.goto('/estandarizacion')
  await expect(page.getByRole('button', { name: /Consolidar y recodificar bases/i })).toHaveCount(0)
  await expect(page.getByRole('heading', { level: 1, name: 'Estandarización ✨' })).toBeVisible()
})
