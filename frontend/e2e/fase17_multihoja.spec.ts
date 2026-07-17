import { expect, test } from '@playwright/test'
import { execFileSync } from 'node:child_process'

function createWorkbook(path: string, unsafe = false) {
  const script = String.raw`
import pandas as pd
import sys
path = sys.argv[1]
unsafe = sys.argv[2] == "1"
ventas = pd.DataFrame({
    "ID Producto": ["A", "A", "B"],
    "Fecha": ["01/01/2026", "02/01/2026", "03/01/2026"],
    "Venta": [1000, 2000, 3000],
})
febrero = ventas.copy()
febrero["Fecha"] = ["01/02/2026", "02/02/2026", "03/02/2026"]
productos = pd.DataFrame({
    "ID Producto": ["A", "A", "B"] if unsafe else ["A", "B"],
    "Producto": ["Uno", "Uno duplicado", "Dos"] if unsafe else ["Uno", "Dos"],
    "Categoria": ["X", "X", "Y"] if unsafe else ["X", "Y"],
})
with pd.ExcelWriter(path, engine="openpyxl") as writer:
    ventas.to_excel(writer, sheet_name="Enero", index=False)
    febrero.to_excel(writer, sheet_name="Febrero", index=False)
    productos.to_excel(writer, sheet_name="Productos", index=False)
`
  execFileSync('python', ['-c', script, path, unsafe ? '1' : '0'])
}

test('Fase 17 procesa, combina, relaciona y exporta un libro multihoja', async ({ page }, testInfo) => {
  const workbook = testInfo.outputPath('ventas_multihoja.xlsx')
  createWorkbook(workbook)

  await page.goto('/estandarizacion')
    const chooserPromise = page.waitForEvent('filechooser')
    await page.getByRole('button', { name: /Subir archivo/ }).click()
    const chooser = await chooserPromise
    await chooser.setFiles(workbook)

    await expect(page.getByText(/Dataset activo:/)).toBeVisible({ timeout: 60_000 })
    await expect(page.getByText('Todas las hojas')).toBeVisible()
    await page.getByRole('button', { name: 'Preparar hojas seleccionadas' }).click()
    await expect(page.getByText('3 de 3 hojas seleccionadas')).toBeVisible()
    await expect(page.getByText('Estandarizada', { exact: true })).toHaveCount(3, { timeout: 90_000 })

    await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
    const cleanAll = page.getByRole('button', { name: /Limpiar todas las hojas preparadas/ })
    await expect(cleanAll).toBeEnabled({ timeout: 60_000 })
    await cleanAll.click()
    await expect(page.getByRole('button', { name: /Descargar libro completo/ })).toBeVisible({ timeout: 90_000 })
    const downloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: /Descargar libro completo/ }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toMatch(/multihoja_limpio\.xlsx$/)

    await page.getByRole('link', { name: /Resumen/ }).first().click()
    await expect(page.getByText('Datos que estas analizando')).toBeVisible({ timeout: 60_000 })
    await page.getByRole('button', { name: /Varias compatibles/ }).click()
    await expect(page.getByText(/hoja_origen/)).toBeVisible()
    await expect(page.getByText('Evolución de Ingresos')).toBeVisible({ timeout: 90_000 })

    await page.getByRole('button', { name: /Hojas relacionadas/ }).click()
    await expect(page.getByText(/Encontramos una conexion entre/).first()).toBeVisible({ timeout: 90_000 })
    await page.getByRole('button', { name: /Usar esta conexion/ }).first().click()
    await page.getByRole('link', { name: /Explorar datos/ }).first().click()
  await expect(page.getByText('Datos que estas analizando')).toBeVisible()
})

test('Fase 17 bloquea una relacion many-to-many', async ({ page }, testInfo) => {
  const workbook = testInfo.outputPath('ventas_many_to_many.xlsx')
  createWorkbook(workbook, true)

  await page.goto('/estandarizacion')
    const chooserPromise = page.waitForEvent('filechooser')
    await page.getByRole('button', { name: /Subir archivo/ }).click()
    const chooser = await chooserPromise
    await chooser.setFiles(workbook)
    await expect(page.getByText(/Dataset activo:/)).toBeVisible({ timeout: 60_000 })
    await page.getByRole('button', { name: 'Preparar hojas seleccionadas' }).click()
    await expect(page.getByText('Estandarizada', { exact: true })).toHaveCount(3, { timeout: 90_000 })
    await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
    await page.getByRole('button', { name: /Limpiar todas las hojas preparadas/ }).click()
    await page.getByRole('link', { name: /Resumen/ }).first().click()
    await page.getByRole('button', { name: /Hojas relacionadas/ }).click()
    await expect(page.getByText(/No encontramos una conexion segura/)).toBeVisible({ timeout: 90_000 })
  await expect(page.getByRole('button', { name: /Usar esta conexion/ })).toHaveCount(0)
})
