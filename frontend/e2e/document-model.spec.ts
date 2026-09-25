import { expect, test } from '@playwright/test'
import { execFileSync } from 'node:child_process'

for (const repeatedCatalog of [false, true]) {
test(`Cabecera-detalle conserva importes y muestra costo documentado, catalogo repetido: ${repeatedCatalog}`, async ({ page }, testInfo) => {
  const path = testInfo.outputPath('documentos_sinteticos.xlsx')
  execFileSync('python', ['-c', String.raw`
import sys, runpy
sys.path.insert(0, '../api')
fixture = runpy.run_path('../api/tests/test_document_line_model.py')
frames = fixture['_frames']()
frames['Detalle_T1']['CostoUnitario_CLP'] = 20
frames['Detalle_T2']['CostoUnitario_CLP'] = 30
import pandas as pd
if sys.argv[2] == 'true':
    frames['Productos'] = pd.concat([frames['Productos'], frames['Productos'].assign(CostoUnitario_CLP=999)], ignore_index=True)
with pd.ExcelWriter(sys.argv[1], engine='openpyxl') as writer:
    for name, frame in frames.items():
        frame.to_excel(writer, sheet_name=name, index=False)
`, path, String(repeatedCatalog)])
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/estandarizacion')
  const chooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /Subir archivo/ }).click()
  await (await chooser).setFiles(path)
  await expect(page.getByText('Estandarizada', { exact: true })).toHaveCount(6, { timeout: 120_000 })
  await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
  await expect(page.getByRole('button', { name: 'Limpiar datos', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Limpiar datos', exact: true }).click()
  await expect(page.getByText(/Todas las hojas están limpias/)).toBeVisible({ timeout: 120_000 })
  let releaseRelations!: () => void
  const relationsGate = new Promise<void>(resolve => { releaseRelations = resolve })
  await page.route('**/sheets/relationships', async route => {
    await relationsGate
    await route.continue()
  })
  await page.getByRole('link', { name: /Explorar datos/ }).first().click()
  await expect(page.getByText('Buscando conexiones seguras entre las hojas', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'No existen conexiones seguras entre las hojas.' })).toBeHidden()
  releaseRelations()
  const analysis = page.getByTestId('exploration-analysis')
  await expect(analysis.getByText('900 CLP', { exact: false }).first()).toBeVisible({ timeout: 60_000 })
  if (repeatedCatalog) await expect(page.getByText(/La unión con el catálogo está bloqueada/)).toBeVisible()
  await page.getByRole('link', { name: /Resumen/ }).first().click()
  const cards = page.getByLabel('Indicadores del negocio', { exact: true })
  await expect(cards.getByText('Costo de ventas documentado', { exact: true })).toBeVisible()
  await expect(cards.getByText('$900', { exact: true })).toBeVisible()
  await expect(cards.getByText('$220', { exact: true })).toBeVisible()
  await expect(cards.getByText('$680', { exact: true })).toBeVisible()
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const overflow = await cards.locator('p').evaluateAll(nodes => nodes
      .filter(node => node.clientWidth > 0 && node.scrollWidth > node.clientWidth + 2)
      .map(node => node.textContent))
    expect(overflow).toEqual([])
    await cards.scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath(`documentos-${width}.png`), fullPage: true })
  }
  expect(errors).toEqual([])
})
}
