import { expect, test } from '@playwright/test'

test('el reporte imprime con CSP restrictiva, sin scripts inline ni desbordamientos', async ({ page }, testInfo) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Ver demo ficticia' }).click()
  const reportRequests: string[] = []
  page.on('request', request => {
    if (/\/analysis\/|\/rest\/v1\/profiles/.test(request.url())) reportRequests.push(request.url())
  })
  await page.getByRole('link', { name: 'Reportes', exact: true }).first().click()
  await expect(page.getByRole('button', { name: 'Generar PDF' })).toBeEnabled()
  await page.evaluate(() => {
    const open = window.open.bind(window)
    window.open = (...args: Parameters<typeof window.open>) => {
      const popup = open(...args)
      if (popup) popup.print = () => { popup.document.documentElement.dataset.printInvoked = 'true' }
      return popup
    }
    const policy = document.createElement('meta')
    policy.httpEquiv = 'Content-Security-Policy'
    policy.content = "script-src 'self'; object-src 'none'"
    document.head.appendChild(policy)
  })
  const popupPromise = page.waitForEvent('popup')
  await page.getByRole('button', { name: 'Generar PDF' }).click()
  const popup = await popupPromise
  await expect(popup.locator('html')).toHaveAttribute('data-print-invoked', 'true')
  await expect(popup.getByText('Moneda: CLP', { exact: true })).toBeVisible()
  await expect(popup.getByText('Comercial Andes SpA (empresa ficticia)', { exact: true })).toBeVisible()
  await expect(popup.locator('script')).toHaveCount(0)
  expect(await popup.evaluate(() => window.opener === null)).toBe(true)
  for (const width of [1280, 320]) {
    await popup.setViewportSize({ width, height: 900 })
    expect(await popup.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    const overflow = await popup.locator('.kpi, td, th, .meta').evaluateAll(elements => elements
      .filter(el => el.scrollWidth > el.clientWidth + 2).map(el => el.textContent))
    expect(overflow).toEqual([])
    await popup.screenshot({ path: testInfo.outputPath(`print-${width}.png`), fullPage: true })
  }
  await popup.close()
  expect(reportRequests).toEqual([])
})
