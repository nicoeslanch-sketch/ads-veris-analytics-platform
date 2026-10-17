import { expect, test } from '@playwright/test'

for (const scope of ['single', 'ledger']) test(`Banco adaptativo: ${scope}, gráficos reales y etiquetas contenidas`, async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(`/e2e/fixtures/exploration-bank.html?scope=${scope}&currency=UF`)
  const bank = page.getByTestId('exploration-chart-bank')
  const select = bank.getByLabel('Pregunta de análisis')
  await expect(select).toHaveValue('recurring-peak')
  const options = await select.locator('option').evaluateAll(nodes => nodes.map(node => (node as HTMLOptionElement).value))
  expect(options.length).toBeGreaterThanOrEqual(7)
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 960 })
    for (const option of options) {
      await select.selectOption(option)
      if (option.endsWith('calendar')) await expect(bank.locator('table').first().locator('tbody td').first()).toBeVisible()
      else await expect(bank.locator('.recharts-surface').first()).toBeVisible()
      const marks = await bank.locator('.recharts-bar-rectangle, .recharts-line-curve, .recharts-scatter-symbol, table tbody td').count()
      expect(marks).toBeGreaterThan(0)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
      const overflow = await bank.locator('p,h2,h3,select,summary').evaluateAll(nodes => nodes.filter(node => node.clientWidth > 0 && node.scrollWidth > node.clientWidth + 2).map(node => node.textContent))
      expect(overflow).toEqual([])
      await bank.screenshot({ path: info.outputPath(`${scope}-${option}-${width}.png`) })
    }
  }
  await select.selectOption('product-calendar')
  await bank.getByText('Ver valores exactos', { exact: true }).click()
  await expect(bank.getByRole('region', { name: 'Valores del gráfico' })).toContainText('UF')
  expect(errors).toEqual([])
})
