import { expect, test } from '@playwright/test'
import { execFileSync } from 'node:child_process'

function createDocumentWorkbook(path: string, repeatedCatalog = false) {
  execFileSync('python', ['-c', String.raw`
import sys, runpy
sys.path.insert(0, '../api')
fixture = runpy.run_path('../api/tests/test_document_line_model.py')
frames = fixture['_frames']()
frames['Detalle_T1']['CostoUnitario_CLP'] = 20
frames['Detalle_T2']['CostoUnitario_CLP'] = 30
import pandas as pd
frames['CxC'] = pd.DataFrame({
    'IDCxC': ['R1', 'R2', 'R3', 'R4', 'R5'],
    'IDVenta': ['V1', 'V3', 'V2', 'V1', 'V1'],
    'MontoOriginal_CLP': [500, 400, 100, 500, 500],
    'Saldo_CLP': [200, 100, 50, -10, 60],
    'EstadoCxC': ['Pendiente', 'Pendiente', 'Pendiente', 'Pendiente', 'Pagada'],
})
if sys.argv[2] == 'true':
    frames['Productos'] = pd.concat([frames['Productos'], frames['Productos'].assign(CostoUnitario_CLP=999)], ignore_index=True)
with pd.ExcelWriter(sys.argv[1], engine='openpyxl') as writer:
    for name, frame in frames.items():
        frame.to_excel(writer, sheet_name=name, index=False)
`, path, String(repeatedCatalog)])
}

for (const repeatedCatalog of [false, true]) {
test(`Cabecera-detalle conserva importes y muestra costo documentado, catalogo repetido: ${repeatedCatalog}`, async ({ page }, testInfo) => {
  const path = testInfo.outputPath('documentos_sinteticos.xlsx')
  createDocumentWorkbook(path, repeatedCatalog)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/estandarizacion')
  const chooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /Subir archivo/ }).click()
  await (await chooser).setFiles(path)
  await expect(page.getByText('Estandarizada', { exact: true })).toHaveCount(7, { timeout: 120_000 })
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
  await expect(cards.getByText('$300', { exact: true })).toBeVisible()
  await expect(cards.getByText('2 cuentas pendientes · sin fecha de corte', { exact: true })).toBeVisible()
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const overflow = await cards.locator('p').evaluateAll(nodes => nodes
      .filter(node => node.clientWidth > 0 && node.scrollWidth > node.clientWidth + 2)
      .map(node => node.textContent))
    expect(overflow).toEqual([])
    await cards.scrollIntoViewIfNeeded()
    await cards.getByText('Cuentas por cobrar', { exact: true }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath(`documentos-${width}.png`), fullPage: true })
  }
  expect(errors).toEqual([])
})
}

for (const scenario of [
  { view: 'Resumen', failure: 'network', empty: false },
  { view: 'Explorar datos', failure: 'capacity', empty: false },
  { view: 'Explorar datos', failure: 'network', empty: true },
]) {
test(`La validacion fallida no se confunde con hojas sin relaciones: ${scenario.view}, vacias: ${scenario.empty}`, async ({ page }, testInfo) => {
  const path = testInfo.outputPath('reintento_sintetico.xlsx')
  createDocumentWorkbook(path)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/estandarizacion')
  const chooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /Subir archivo/ }).click()
  await (await chooser).setFiles(path)
  await expect(page.getByText('Estandarizada', { exact: true })).toHaveCount(7, { timeout: 120_000 })
  await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
  await page.getByRole('button', { name: 'Limpiar datos', exact: true }).click()
  await expect(page.getByText(/Todas las hojas están limpias/)).toBeVisible({ timeout: 120_000 })
  let attempts = 0
  let releaseRetry!: () => void
  const retryGate = new Promise<void>(resolve => { releaseRetry = resolve })
  const focusSelections: string[] = []
  await page.route('**/sheets/relationships', async route => {
    attempts += 1
    const body = route.request().postData() ?? ''
    focusSelections.push(body.match(/name="focus"\r?\n\r?\n([^\r\n]+)/)?.[1] ?? '')
    if (attempts === 1) {
      if (scenario.failure === 'network') await route.abort('failed')
      else await route.fulfill({ status: 429, contentType: 'application/json', body: JSON.stringify({ detail: 'Hay un cálculo en curso. Vuelve a intentar en unos segundos.' }) })
      return
    }
    await retryGate
    if (scenario.empty) await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ candidates: [], safe_count: 0, message: 'Sin correspondencias validadas.' }) })
    else await route.continue()
  })
  await page.getByRole('link', { name: scenario.view, exact: true }).first().click()
  await expect(page.getByText('No pudimos validar las conexiones.', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'El análisis conjunto sigue pendiente' })).toBeVisible()
  await expect(page.getByText('No existen conexiones seguras entre las hojas.', { exact: true })).toHaveCount(0)
  await page.setViewportSize({ width: 320, height: 900 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  const headingLines = await page.getByRole('alert').getByText('No pudimos validar las conexiones.', { exact: true }).evaluate(node =>
    node.getBoundingClientRect().height / parseFloat(getComputedStyle(node).lineHeight))
  expect(headingLines).toBeLessThanOrEqual(3)
  await page.screenshot({ path: testInfo.outputPath('error-conexiones-320.png'), fullPage: true })
  await page.setViewportSize({ width: 1280, height: 900 })
  const retry = page.getByRole('button', { name: 'Reintentar conexiones', exact: true })
  await retry.click()
  await expect(page.getByText('Buscando conexiones seguras entre las hojas', { exact: true })).toBeVisible()
  await expect(retry).toBeHidden()
  await expect(page.getByRole('heading', { name: 'El análisis conjunto sigue pendiente' })).toBeHidden()
  releaseRetry()
  if (scenario.empty) {
    await expect(page.getByRole('heading', { name: 'No existen conexiones seguras entre las hojas.' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'El análisis conjunto sigue pendiente' })).toBeHidden()
  } else if (scenario.view === 'Resumen') {
    await expect(page.getByLabel('Indicadores del negocio', { exact: true }).getByText('$900', { exact: true })).toBeVisible({ timeout: 60_000 })
  } else {
    await expect(page.getByTestId('exploration-analysis').getByText('900 CLP', { exact: false }).first()).toBeVisible({ timeout: 60_000 })
  }
  expect(attempts).toBe(2)
  expect(focusSelections[0]).not.toBe('')
  expect(focusSelections[1]).toBe(focusSelections[0])
  await expect(page.getByText('No pudimos validar las conexiones.', { exact: true })).toHaveCount(0)
  expect(errors).toEqual([])
})
}
