import { test, expect } from '@playwright/test'

for (const width of [390, 1280]) {
  test(`catalog counts explain rows and preserve long values at ${width}px`, async ({ page }) => {
    await page.setViewportSize({width, height: 900})
    await page.goto('/e2e/fixtures/catalog-layout.html')
    await expect(page.getByText('Estado (registros)', {exact:true})).toBeVisible()
    await expect(page.getByText(/5 registros\. Productos cuenta valores distintos de Producto/)).toBeVisible()
    await expect(page.getByText('Costo catálogo (1 unidad/fila)', {exact:true})).toBeVisible()
    await expect(page.getByText('Registros inactivos en la maestra', {exact:true})).toBeVisible()
    await expect(page.getByText('Registros por categoría.', {exact:true})).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const values = page.locator('p').filter({hasText: '$987.654.321.012.345'})
    await expect(values).toHaveCount(1)
    expect(await values.evaluateAll(elements => elements.every(element => element.scrollWidth <= element.clientWidth + 1))).toBe(true)
    await expect(page.locator('.recharts-pie-sector')).toHaveCount(2)
    await page.screenshot({path:`test-results/catalog-grain-${width}.png`, fullPage:true})
  })
}

test('catalog references keep UF instead of implying pesos', async ({page}) => {
  await page.goto('/e2e/fixtures/catalog-layout.html?currency=UF')
  await expect(page.getByText('UF 220', {exact:true})).toBeVisible()
  expect(await page.locator('main').innerText()).not.toContain('$')
})
