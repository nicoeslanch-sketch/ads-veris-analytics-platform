import { expect, test } from '@playwright/test'
import { execFileSync } from 'node:child_process'

test('Libro relacional: limpieza, periodos, graficos, navegacion y ayuda humana', async ({ page }, testInfo) => {
  const path = testInfo.outputPath('libro_relacional.xlsx')
  execFileSync('python', ['-c', String.raw`
import sys, runpy, pandas as pd
sys.path.insert(0, '../api')
frames = runpy.run_path('../api/tests/test_relational_ledger.py')['workbook_frames']()
names = {'sales':'VENTAS', 'lines':'DET_VENTAS', 'credits':'NOTAS_CREDITO', 'returns':'DET_DEVOLUCIONES',
         'lots':'LOTES', 'products':'PRODUCTOS', 'categories':'CATEGORIAS', 'branches':'SUCURSALES', 'employees':'EMPLEADOS'}
with pd.ExcelWriter(sys.argv[1], engine='openpyxl') as writer:
    for name, frame in frames.items():
        if not frame.empty:
            frame.to_excel(writer, sheet_name=names[name], index=False)
`, path])
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/estandarizacion')
  const chooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /Subir archivo/ }).click()
  await (await chooser).setFiles(path)
  await expect(page.getByText('Estandarizada', { exact: true })).toHaveCount(9, { timeout: 120_000 })
  await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
  await page.getByRole('button', { name: 'Limpiar datos', exact: true }).click()
  await expect(page.getByText(/Todas las hojas están limpias/)).toBeVisible({ timeout: 120_000 })
  await page.getByRole('link', { name: 'Resumen', exact: true }).first().click()
  const panel = page.getByTestId('relational-ledger')
  await expect(panel).toBeVisible({ timeout: 90_000 })
  await expect(panel.getByText('200 CLP', { exact: true })).toBeVisible()
  await expect(panel.getByText('120 CLP', { exact: true })).toBeVisible()
  const period = panel.getByLabel('Período del negocio')
  await period.selectOption('2025')
  await expect(panel.getByText('100 CLP', { exact: true })).toBeVisible({ timeout: 60_000 })
  await period.selectOption('2026-02')
  await expect(panel.getByText('-100 CLP', { exact: true })).toBeVisible({ timeout: 60_000 })
  await period.selectOption('all')
  await expect(panel.getByText('200 CLP', { exact: true })).toBeVisible({ timeout: 60_000 })
  await panel.getByLabel('Medida de productos').selectOption('utilidad')
  await expect(panel.getByTestId('ledger-monthly').locator('.recharts-bar-rectangle').first()).toBeVisible()
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const overflow = await panel.locator('p, button, select, h2, h3').evaluateAll(nodes => nodes
      .filter(node => node.clientWidth > 0 && node.scrollWidth > node.clientWidth + 2)
      .map(node => node.textContent))
    expect(overflow).toEqual([])
    await panel.getByTestId('ledger-monthly').screenshot({ path: testInfo.outputPath(`ledger-monthly-${width}.png`) })
    await panel.getByTestId('ledger-ranking').first().screenshot({ path: testInfo.outputPath(`ledger-ranking-${width}.png`) })
  }
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.getByRole('link', { name: 'Explorar datos', exact: true }).first().click()
  await expect(panel.getByRole('heading', { name: 'Decisiones del período' })).toBeVisible()
  await expect(panel.getByRole('heading', { name: /Composición del resultado/ })).toBeVisible()
  await page.getByRole('link', { name: 'Resumen', exact: true }).first().click()
  await expect(panel.getByText('200 CLP', { exact: true })).toBeVisible()
  for (const [question, expected] of [['cuanto vendi', '$200'], ['y en 2025', '$100'],
      ['mi utilidad bruta', '$120'], ['producto mas rentable', '$120'],
      ['como contacto a un humano', 'Abre Ayuda']]) {
    await page.getByPlaceholder('Pregunta por tus cifras o por una función…').fill(question)
    const response = page.waitForResponse(r => new URL(r.url()).pathname === '/assistant/bot' && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Enviar pregunta', exact: true }).click()
    const answer = await response
    expect(answer.status()).toBe(200)
    expect((await answer.json()).answer).toContain(expected)
  }
  expect(errors).toEqual([])
})
