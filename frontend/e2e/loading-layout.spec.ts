import { expect, test } from '@playwright/test'

for (const width of [320, 768, 1440]) {
  test(`skeletons accesibles y sin desbordar a ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 })
    await page.goto('/e2e/fixtures/loading-layout.html')
    await expect(page.getByTestId('skeleton-dashboard')).toBeVisible()
    await expect(page.getByTestId('skeleton-table')).toBeVisible()
    await expect(page.getByRole('status').filter({ hasText: 'Cargando perfil' })).toHaveAttribute('aria-busy', 'true')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect(await page.locator('.loading-skeleton').first().evaluate(el => getComputedStyle(el).animationName)).toBe('skeleton-shimmer')
    await page.screenshot({ path: `test-results/skeleton-${width}.png`, fullPage: true })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    expect(await page.locator('.loading-skeleton').first().evaluate(el => getComputedStyle(el).animationName)).toBe('none')
    await page.getByRole('button', { name: 'Cancelar' }).click()
    await expect(page).toHaveTitle('cancelled')
  })
}

test('menu de cuenta tiene una sola entrada para perfil y configuracion', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Menú de cuenta' }).click()
  await expect(page.getByRole('button', { name: 'Mi perfil', exact: true })).toHaveCount(0)
  const settings = page.getByRole('button', { name: 'Configuración', exact: true })
  await expect(settings).toHaveCount(1)
  await settings.click()
  await expect(page).toHaveURL(/\/configuracion$/)
})
