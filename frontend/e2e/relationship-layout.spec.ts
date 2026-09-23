import { expect, test } from '@playwright/test'

for (const width of [320, 390, 768, 1280, 1600]) {
  test(`Relationship amounts and labels fit at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/e2e/fixtures/relationship-layout.html')
    await expect(page.getByText('$-10.000.079')).toBeVisible()
    await expect(page.getByText('Gastos Operacionales + Sucursales').first()).toBeVisible()
    const values = page.getByLabel('Indicadores de prueba').locator('p[title]')
    await expect(values).toHaveCount(3)
    await expect.poll(() => values.evaluateAll(nodes => nodes.every(node => {
      const style = getComputedStyle(node)
      return style.whiteSpace === 'nowrap' && node.scrollWidth <= node.clientWidth
        && node.getBoundingClientRect().bottom <= node.parentElement!.parentElement!.getBoundingClientRect().bottom
    }))).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `test-results/relationship-${width}.png`, fullPage: true })
  })
}
