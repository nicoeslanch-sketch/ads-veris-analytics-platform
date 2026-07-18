import { expect, test } from '@playwright/test'
import { execFileSync } from 'node:child_process'

function createWorkbook(path: string, unsafe = false) {
  const script = String.raw`
import pandas as pd
import sys
path = sys.argv[1]
unsafe = sys.argv[2] == "1"
ventas = pd.DataFrame({
    "ID Producto": ["A", "A", "B", "B", "C", "C"],
    "Fecha": ["01/01/2026", "02/01/2026", "03/01/2026", "04/01/2026", "05/01/2026", "06/01/2026"],
    "Cantidad": [1, 2, 1, 3, 2, 1],
    "Venta": [1000, 2000, 3000, 4500, 2800, 1600],
})
febrero = ventas.copy()
febrero["Fecha"] = ["01/02/2026", "02/02/2026", "03/02/2026", "04/02/2026", "05/02/2026", "06/02/2026"]
productos = pd.DataFrame({
    "ID Producto": ["A", "A", "B", "C", "D", "E"] if unsafe else ["A", "B", "C", "D", "E"],
    "Producto": ["Uno", "Uno duplicado", "Dos", "Tres", "Cuatro", "Cinco"] if unsafe else ["Uno", "Dos", "Tres", "Cuatro", "Cinco"],
    "Categoria": ["X", "X", "Y", "Y", "Z", "Z"] if unsafe else ["X", "Y", "Y", "Z", "Z"],
    "Costo_Unitario": [500, 550, 1200, 800, 700, 900] if unsafe else [500, 1200, 800, 700, 900],
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
    await expect(page.getByText(/Todas las hojas, con recomendacion/)).toBeVisible()
    await expect(page.getByText('3 de 3 hojas seleccionadas')).toHaveCount(0)
    await expect(page.getByText(/estructuras distintas/i)).toHaveCount(0)
    await expect(page.getByText('Estandarizada', { exact: true })).toHaveCount(3, { timeout: 90_000 })
    await expect(page.getByRole('button', { name: /preparación|Preparar hojas/ })).toHaveCount(0)
    await expect(page.getByText('Enero', { exact: true })).toHaveCount(1)
    await expect(page.getByText('Febrero', { exact: true })).toHaveCount(1)
    await expect(page.getByText('Productos', { exact: true })).toHaveCount(1)

    await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
    await expect(page.getByText(/Todas las hojas están limpias/)).toBeVisible({ timeout: 90_000 })
    await expect(page.getByText('3 limpias', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: /Descargar libro completo/ })).toBeVisible({ timeout: 90_000 })
    const downloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: /Descargar libro completo/ }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toMatch(/multihoja_limpio\.xlsx$/)

    await page.getByRole('link', { name: /Resumen/ }).first().click()
    await expect(page.getByText('Datos que estas analizando')).toBeVisible({ timeout: 60_000 })
    await page.getByRole('button', { name: /Solo apilar ventas/ }).click()
    await expect(page.getByText(/hoja_origen/)).toBeVisible()
    await expect(page.getByText('Evolución de Ingresos')).toBeVisible({ timeout: 90_000 })

    await page.getByRole('button', { name: /Ventas \+ costos/ }).click()
    await expect(page.getByText(/apilamos 2 hojas de ventas y agregamos los costos/i)).toBeVisible({ timeout: 90_000 })
    await expect(page.getByText('Cobertura de Costos')).toBeVisible({ timeout: 90_000 })
    await expect(page.getByText('Costo Conocido')).toBeVisible()
    await expect(page.getByText('$17.400', { exact: true })).toBeVisible()
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
    await expect(page.getByText('Estandarizada', { exact: true })).toHaveCount(3, { timeout: 90_000 })
    await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
    await expect(page.getByText(/Todas las hojas están limpias/)).toBeVisible({ timeout: 90_000 })
    await page.getByRole('link', { name: /Resumen/ }).first().click()
    await page.getByRole('button', { name: /Ventas \+ costos/ }).click()
    await expect(page.getByText(/No encontramos una conexion segura|No encontramos una conexión segura/)).toBeVisible({ timeout: 90_000 })
  await expect(page.getByRole('button', { name: /Apilar y relacionar/ })).toHaveCount(0)
})
