import { expect, test } from '@playwright/test'
import { execFileSync } from 'node:child_process'

/** Libro multihoja con Ventas (Enero/Febrero) + Productos (con costo) +
 * Clientes, para ejercitar la botonera y el workspace de relaciones. */
function createWorkbook(path: string) {
  const script = String.raw`
import pandas as pd
import sys
path = sys.argv[1]
enero = pd.DataFrame({
    "ID Producto": ["A", "A", "B", "C", "B", "A"],
    "ID Cliente": ["C1", "C2", "C1", "C3", "C2", "C1"],
    "Fecha": ["01/01/2026", "05/01/2026", "10/01/2026", "15/01/2026", "20/01/2026", "25/01/2026"],
    "Cantidad": [2, 1, 3, 1, 5, 2],
    "Venta": [2000, 1500, 3000, 900, 7500, 2000],
})
febrero = enero.copy()
febrero["Fecha"] = ["01/02/2026", "05/02/2026", "10/02/2026", "15/02/2026", "20/02/2026", "25/02/2026"]
productos = pd.DataFrame({
    "ID Producto": ["A", "B", "C"],
    "Producto": ["Alfa", "Beta", "Gamma"],
    "Categoria": ["Bebidas", "Snacks", "Bebidas"],
    "Costo_Unitario": [500, 600, 300],
})
clientes = pd.DataFrame({
    "ID Cliente": ["C1", "C2", "C3"],
    "Cliente": ["Uno", "Dos", "Tres"],
})
with pd.ExcelWriter(path, engine="openpyxl") as writer:
    enero.to_excel(writer, sheet_name="Enero", index=False)
    febrero.to_excel(writer, sheet_name="Febrero", index=False)
    productos.to_excel(writer, sheet_name="Productos", index=False)
    clientes.to_excel(writer, sheet_name="Clientes", index=False)
`
  execFileSync('python', ['-c', script, path])
}

test('Fase 20: botonera de 4 modos y workspace de relaciones', async ({ page }, testInfo) => {
  const workbook = testInfo.outputPath('ventas_relaciones.xlsx')
  createWorkbook(workbook)

  await page.goto('/estandarizacion')
  const chooserPromise = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /Subir archivo/ }).click()
  const chooser = await chooserPromise
  await chooser.setFiles(workbook)

  await expect(page.getByText(/Dataset activo:/)).toBeVisible({ timeout: 60_000 })
  await expect(page.getByText('Estandarizada', { exact: true })).toHaveCount(4, { timeout: 120_000 })

  await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
  await expect(page.getByText('Problemas detectados')).toBeVisible({ timeout: 90_000 })
  const cleanAllButton = page.getByRole('button', { name: 'Limpiar datos', exact: true })
  await expect(cleanAllButton).toBeEnabled()
  await cleanAllButton.click()
  await expect(page.getByText(/Todas las hojas están limpias/)).toBeVisible({ timeout: 120_000 })

  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.getByRole('link', { name: /Resumen/ }).first().click()
  await expect(page.getByText('Datos que estas analizando')).toBeVisible({ timeout: 60_000 })

  // Los cuatro modos existen (Parte 15.1).
  for (const label of ['Analizar una hoja', 'Visión del negocio', 'Unir periodos de venta', 'Relación manual']) {
    await expect(page.getByRole('button', { name: label })).toBeVisible()
  }

  // "Unir periodos de venta" y "Visión del negocio" conservan su comportamiento.
  await page.getByRole('button', { name: 'Unir periodos de venta' }).click()
  await expect(page.getByText(/hoja_origen/)).toBeVisible({ timeout: 90_000 })
  await page.getByRole('button', { name: 'Visión del negocio' }).click()
  await expect(page.getByText('Ventas + costos activo')).toBeVisible({ timeout: 120_000 })

  // "Relación manual" abre el workspace: catálogo + dashboard.
  await page.getByRole('button', { name: 'Relación manual' }).click()
  await expect(page.getByText('Selecciona una conexión')).toBeVisible({ timeout: 120_000 })
  await expect(page.getByRole('button', { name: /Crear conexión personalizada/ })).toBeVisible()
  // El dashboard de la relación recomendada se calcula solo (Ventas ↔ Productos).
  await expect(page.getByText('Conexión segura')).toBeVisible({ timeout: 120_000 })
})
