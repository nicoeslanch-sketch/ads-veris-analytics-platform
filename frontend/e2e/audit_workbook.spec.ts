import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

test('auditoria opcional del libro desafiante real', async ({ page }, testInfo) => {
  const workbook = process.env.ADS_AUDIT_WORKBOOK
  const referencePath = process.env.ADS_AUDIT_REFERENCE
  test.skip(!workbook || !referencePath, 'Requires a local workbook and independently reviewed audit JSON, never committed to the repo.')
  const reference = JSON.parse(readFileSync(referencePath!, 'utf-8')) as { sheets: Array<{ sheet: string; metrics: { kpis: { ingresos_totales: { valor: number } }; analisis_generico?: { numericas: Array<{ columna: string; total: number }> } } }> }
  const money = (value: number) => `$${new Intl.NumberFormat('es-CL', { maximumFractionDigits: 0 }).format(value)}`
  const income = (sheet: string) => money(reference.sheets.find((item) => item.sheet === sheet)!.metrics.kpis.ingresos_totales.valor)
  const expense = reference.sheets.find((item) => item.sheet === 'Gastos_Operacionales')!.metrics.analisis_generico!.numericas.find((item) => item.columna === 'Total Gasto')!.total
  test.setTimeout(600_000)
  page.setDefaultTimeout(30_000)
  const batches: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().includes('/batch/jobs')) batches.push(request.url())
  })
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/estandarizacion')
  const chooserPromise = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /Subir archivo/ }).click()
  await (await chooserPromise).setFiles(workbook!)
  await expect(page.getByText('Estandarizada', { exact: true })).toHaveCount(16, { timeout: 180_000 })
  console.log('Workbook standardized')
  await page.getByLabel('Procesar hoja Parametros', { exact: true }).uncheck()
  await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
  await expect(page.getByText('Problemas detectados')).toBeVisible({ timeout: 180_000 })
  await page.getByRole('button', { name: 'Limpiar datos', exact: true }).click()
  await expect(page.getByText('15 limpias', { exact: true })).toBeVisible({ timeout: 180_000 })
  console.log('All 15 data sheets cleaned')
  expect(batches.some((url) => url.includes('/standardize/batch/jobs'))).toBe(true)
  expect(batches.some((url) => url.includes('/clean/batch/jobs'))).toBe(true)
  await page.getByRole('link', { name: /Resumen/ }).first().click()
  await page.getByRole('combobox', { name: 'Hoja', exact: true }).selectOption('Ventas_2024')
  await expect(page.getByText(income('Ventas_2024'), { exact: true }).first()).toBeVisible({ timeout: 120_000 })
  await expect(page.getByText('Analizar una hoja · Ventas_2024', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: /Explorar datos/ }).first().click()
  await expect(page.getByRole('combobox', { name: 'Hoja', exact: true })).toHaveValue('Ventas_2024')
  await page.getByRole('link', { name: /Resumen/ }).first().click()
  await expect(page.getByRole('button', { name: 'Analizar una hoja', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('combobox', { name: 'Hoja', exact: true }).selectOption('Ventas_2025')
  await expect(page.getByText(income('Ventas_2025'), { exact: true }).first()).toBeVisible({ timeout: 120_000 })
  await expect(page.getByText('Analizar una hoja · Ventas_2025', { exact: true })).toBeVisible()
  const statusChart = page.getByRole('heading', { name: 'Ventas por Estado', exact: true }).locator('..').locator('..')
  await expect(statusChart).toBeVisible()
  await expect(statusChart.getByText('103,3%', { exact: true })).toHaveCount(0)
  await statusChart.screenshot({ path: testInfo.outputPath('ventas-estado.png') })
  console.log('Sales and active-sheet scope reconciled')
  await page.getByRole('combobox', { name: 'Hoja', exact: true }).selectOption('Gastos_Operacionales')
  await expect(page.getByText(money(expense), { exact: true }).first()).toBeVisible({ timeout: 120_000 })
  const breakdown = page.getByLabel('Desglose operativo')
  await expect(breakdown).toBeVisible()
  const breakdownCard = page.locator('[data-dashboard-card]').filter({ has: breakdown })
  const expectClearToolbar = async () => {
    await expect(breakdownCard.getByRole('button', { name: 'Ampliar gráfico', exact: true })).toBeVisible()
    const overlaps = await breakdownCard.evaluate((card) => {
      const header = card.firstElementChild!
      const controls = [...card.querySelectorAll('.dashboard-card-actions button'), ...document.querySelectorAll('.dashboard-expanded-close')]
      const contents = [header, ...header.querySelectorAll('h2,h3,h4,select')]
      return contents.some((content) => controls.some((control) => {
        const a = content.getBoundingClientRect()
        const b = control.getBoundingClientRect()
        // The header reserves padding; only its content box must stay clear.
        const right = content === header ? a.right - parseFloat(getComputedStyle(header).paddingRight) : a.right
        return a.left < b.right && right > b.left && a.top < b.bottom && a.bottom > b.top
      }))
    })
    expect(overlaps).toBe(false)
  }
  await page.setViewportSize({ width: 1280, height: 720 })
  await breakdownCard.hover()
  await expectClearToolbar()
  await breakdownCard.getByRole('button', { name: 'Ampliar gráfico', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Cerrar gráfico ampliado' })).toBeVisible()
  await expectClearToolbar()
  await page.getByRole('button', { name: 'Cerrar gráfico ampliado' }).click()
  await breakdown.scrollIntoViewIfNeeded()
  await page.screenshot({ path: testInfo.outputPath('gastos-desktop.png') })
  await page.setViewportSize({ width: 390, height: 844 })
  await breakdown.scrollIntoViewIfNeeded()
  await breakdown.focus()
  await expectClearToolbar()
  const overflow = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, viewport: innerWidth }))
  expect(overflow.content).toBeLessThanOrEqual(overflow.viewport + 1)
  await page.screenshot({ path: testInfo.outputPath('gastos-mobile.png') })
  console.log('Operational dashboard verified on desktop and mobile')
})
