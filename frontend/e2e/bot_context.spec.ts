import { expect, test, type Page, type Route } from '@playwright/test'
import { execFileSync } from 'node:child_process'

interface BotRequest {
  message: string
  historial: Array<{ role: string; content: string }>
  metrics: { kpis: { ingresos_totales: { valor: number } }; periodo: unknown } | null
}

function botPanel(page: Page) {
  return page.getByRole('complementary').filter({ has: page.getByRole('heading', { name: 'Asistente ADS Veris' }) })
}

async function reply(route: Route, answer: string, suggestions: string[] = ['Ver siguiente detalle']) {
  await route.fulfill({
    json: { answer, suggestions, confidence: 'high', coins_charged: 0, knowledge_articles: 91 },
  })
}

async function ask(page: Page, question: string) {
  const panel = botPanel(page)
  const input = panel.getByPlaceholder('Pregunta por tus cifras o por una función…')
  await expect(input).toBeEnabled()
  await input.fill(question)
  await panel.getByRole('button', { name: 'Enviar pregunta', exact: true }).click()
}

test('el bot conserva el hilo, renueva sugerencias y permite empezar una conversacion limpia', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const requests: BotRequest[] = []
  await page.route('**/assistant/bot', async (route) => {
    requests.push(route.request().postDataJSON())
    await reply(route, `Respuesta de prueba ${requests.length}`, [`Continuar consulta ${requests.length}`])
  })
  await page.goto('/')
  const panel = botPanel(page)
  await expect(panel.getByRole('button', { name: 'Nueva conversación' })).toBeDisabled()
  await ask(page, 'Como conecto Google Sheets')
  await expect(panel.getByText('Respuesta de prueba 1', { exact: true })).toBeVisible()
  await panel.getByRole('button', { name: 'Continuar consulta 1', exact: true }).click()
  await expect(panel.getByText('Respuesta de prueba 2', { exact: true })).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Continuar consulta 2', exact: true })).toBeVisible()
  expect(requests[0].historial).toEqual([])
  expect(requests[1].historial).toEqual([
    { role: 'user', content: 'Como conecto Google Sheets' },
    { role: 'assistant', content: 'Respuesta de prueba 1' },
  ])
  await panel.getByRole('button', { name: 'Nueva conversación' }).click()
  await expect(panel.getByText('Respuesta de prueba 1', { exact: true })).toHaveCount(0)
  await expect(panel.getByText('Respuesta de prueba 2', { exact: true })).toHaveCount(0)
  await ask(page, 'Que puedo descargar')
  await expect(panel.getByText('Respuesta de prueba 3', { exact: true })).toBeVisible()
  expect(requests[2].historial).toEqual([])
})

test('cambiar hoja y periodo descarta respuestas pendientes y no mezcla historiales ni cifras', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const workbook = testInfo.outputPath('bot-contexto.xlsx')
  execFileSync('python', ['-c', String.raw`
import pandas as pd
import sys
with pd.ExcelWriter(sys.argv[1], engine="openpyxl") as writer:
    for sheet, factor in [("Ventas_A", 1), ("Ventas_B", 10)]:
        pd.DataFrame({
            "Fecha": ["01/01/2026", "02/01/2026", "01/02/2026", "02/02/2026"],
            "ID Venta": ["V1", "V2", "V3", "V4"],
            "Producto": ["A", "B", "A", "B"],
            "Cantidad": [1, 1, 1, 1],
            "Monto Venta": [100 * factor, 200 * factor, 300 * factor, 400 * factor],
        }).to_excel(writer, sheet_name=sheet, index=False)
`, workbook])
  const requests: BotRequest[] = []
  let pending: Route | null = null
  await page.route('**/assistant/bot', async (route) => {
    const request = route.request().postDataJSON() as BotRequest
    requests.push(request)
    if (request.message.startsWith('Consulta pendiente')) {
      pending = route
      return
    }
    await reply(route, `Cifras verificadas: ${request.metrics?.kpis.ingresos_totales?.valor}`)
  })

  await page.goto('/estandarizacion')
  const chooserPromise = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /Subir archivo/ }).click()
  await (await chooserPromise).setFiles(workbook)
  await expect(page.getByText('Estandarizada', { exact: true })).toHaveCount(2, { timeout: 90_000 })
  await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
  await page.getByRole('button', { name: 'Limpiar datos', exact: true }).click()
  await expect(page.getByText(/Todas las hojas están limpias/)).toBeVisible({ timeout: 90_000 })
  await page.getByRole('link', { name: /Explorar datos/ }).first().click()
  await page.getByRole('combobox', { name: 'Hoja', exact: true }).selectOption('Ventas_A')
  await expect(page.getByRole('combobox', { name: 'Hoja', exact: true })).toHaveValue('Ventas_A')
  const panel = botPanel(page)
  await ask(page, 'Mis ingresos iniciales')
  await expect(panel.getByText('Cifras verificadas: 1000', { exact: true })).toBeVisible()

  await ask(page, 'Consulta pendiente de la hoja anterior')
  await expect.poll(() => pending !== null).toBe(true)
  await page.getByRole('combobox', { name: 'Hoja', exact: true }).selectOption('Ventas_B')
  await expect(panel.getByText('Cifras verificadas: 1000', { exact: true })).toHaveCount(0)
  await expect(panel.getByText('Consulta pendiente de la hoja anterior', { exact: true })).toHaveCount(0)
  const oldSheetRequest = pending as unknown as Route
  pending = null
  await reply(oldSheetRequest, 'Respuesta obsoleta de Ventas_A').catch(() => undefined)
  await ask(page, 'Mis ingresos de la nueva hoja')
  await expect(panel.getByText('Cifras verificadas: 10000', { exact: true })).toBeVisible()
  expect(requests.at(-1)?.historial).toEqual([])
  await expect(panel.getByText('Respuesta obsoleta de Ventas_A', { exact: true })).toHaveCount(0)

  await ask(page, 'Consulta pendiente sin filtro')
  await expect.poll(() => pending !== null).toBe(true)
  await page.getByLabel('Período del análisis').selectOption('2026-02')
  await expect(panel.getByText('Cifras verificadas: 10000', { exact: true })).toHaveCount(0)
  await expect(panel.getByText('Consulta pendiente sin filtro', { exact: true })).toHaveCount(0)
  const oldPeriodRequest = pending as unknown as Route
  pending = null
  await reply(oldPeriodRequest, 'Respuesta obsoleta del periodo completo').catch(() => undefined)
  await ask(page, 'Mis ingresos filtrados')
  await expect(panel.getByText('Cifras verificadas: 7000', { exact: true })).toBeVisible()
  expect(requests.at(-1)?.historial).toEqual([])
  await expect(panel.getByText('Respuesta obsoleta del periodo completo', { exact: true })).toHaveCount(0)
})

test('las conversaciones y sugerencias largas se ajustan al panel movil', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const longWord = 'DatoFinanciero'.repeat(70)
  const longSuggestion = `Comparar ${'NombreDeProducto'.repeat(30)}`
  await page.route('**/assistant/bot', (route) => reply(route, longWord, [longSuggestion]))
  await page.goto('/')
  await page.getByRole('button', { name: 'Abrir Asistente IA', exact: true }).click()
  const panel = botPanel(page)
  await ask(page, 'ConsultaDeIngresosSinEspacios'.repeat(25))
  await expect(panel.getByText(longWord, { exact: true })).toBeVisible()
  await expect(panel.getByRole('button', { name: longSuggestion, exact: true })).toBeVisible()
  const overflow = await panel.evaluate((root) => [root, ...root.querySelectorAll('div, p, button, textarea')]
    .filter((element) => element.getBoundingClientRect().width > 0 && element.scrollWidth > element.clientWidth + 2)
    .map((element) => ({ tag: element.tagName, text: element.textContent?.slice(0, 100) })))
  expect(overflow).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('bot-mobile-long-conversation.png') })
})
