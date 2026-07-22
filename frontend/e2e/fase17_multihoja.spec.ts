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

function createDuplicateWorkbook(path: string) {
  const script = String.raw`
import pandas as pd
import sys
path = sys.argv[1]
rows = pd.DataFrame({
    "ID Venta": ["V-1", "V-2", "V-2", "V-3"],
    "Fecha": ["01/01/2026", "02/01/2026", "02/01/2026", "03/01/2026"],
    "Producto": ["A", "B", "B", "C"],
    "Monto": [1000, 2000, 2000, 3000],
})
rows.to_excel(path, sheet_name="Ventas", index=False)
`
  execFileSync('python', ['-c', script, path])
}

function createBatchDuplicateWorkbook(path: string) {
  const script = String.raw`
import pandas as pd
import sys
path = sys.argv[1]
ventas_a = pd.DataFrame({
    "ID Venta": ["A-1", "A-2", "A-2"],
    "Fecha": ["01/01/2026", "02/01/2026", "02/01/2026"],
    "SKU_Producto": ["SKU-1", "SKU-2", "SKU-2"],
    "Monto": [1000, 2000, 2000],
})
ventas_b = pd.DataFrame({
    "ID Venta": ["B-1", "B-1", "B-2"],
    "Fecha": ["03/01/2026", "03/01/2026", "04/01/2026"],
    "SKU_Producto": ["SKU-1", "SKU-1", "SKU-2"],
    "Monto": [1500, 1500, 2500],
})
costos = pd.DataFrame({
    "SKU_Producto": ["SKU-1", "SKU-2"],
    "Costo Unitario": [500, 900],
    "Fecha Vigencia": ["01/01/2026", "01/01/2026"],
})
with pd.ExcelWriter(path, engine="openpyxl") as writer:
    ventas_a.to_excel(writer, sheet_name="Ventas_A", index=False)
    ventas_b.to_excel(writer, sheet_name="Ventas_B", index=False)
    costos.to_excel(writer, sheet_name="Costos_Productos", index=False)
`
  execFileSync('python', ['-c', script, path])
}

function createProviderWorkbook(path: string) {
  const script = String.raw`
import pandas as pd
import sys
pd.DataFrame({
    "ID_Proveedor": ["P-1", "P-2", "P-3"],
    "Razón Social": ["Uno SpA", "Dos Ltda", "Tres SpA"],
    "Categoría Principal": ["Aseo", "Oficina", "Aseo"],
    "Región": ["Maule", "Biobío", "Maule"],
    "Condición Pago Días": [15, 30, 60],
    "Activo": ["Sí", "Sí", "No"],
}).to_excel(sys.argv[1], sheet_name="Proveedores", index=False)
`
  execFileSync('python', ['-c', script, path])
}

function standardizationResponse(filename: string, value: string) {
  return {
    archivo: filename,
    avisos: [],
    cambios: {
      celdas_con_espacios_normalizados: 0,
      celdas_con_variantes_unificadas: 0,
      celdas_textuales_unicas_modificadas: 0,
      encabezados_normalizados: 0,
      equivalencias_canal: 0,
      fechas_estandarizadas: 0,
      fusiones_fuzzy: 0,
      mojibake_detectado: 0,
      mojibake_reparado: 0,
      numeros_estandarizados: 0,
      placeholders_detectados: 0,
      textos_normalizados: 0,
    },
    carga: {
      clasificacion_hojas: [],
      filas_titulo_omitidas: 0,
      formulas: null,
      hoja_usada: null,
      hojas_disponibles: [],
    },
    column_confidence: { Valor: 1 },
    column_types: { Valor: 'texto' },
    columnas: 1,
    filas: 1,
    mapeo: {},
    mapeo_extendido: {},
    mojibake_auditoria: [],
    preview: {
      antes: [[value]],
      columnas: ['Valor'],
      despues: [[value]],
    },
  }
}

test('el ultimo archivo elegido prevalece aunque una carga anterior responda despues', async ({ page }) => {
  let previousRequestStarted = false
  await page.route('**/standardize', async (route) => {
    const body = route.request().postData() ?? ''
    const previous = body.includes('archivo_anterior.csv')
    if (previous) {
      previousRequestStarted = true
      await new Promise((resolve) => setTimeout(resolve, 1_000))
    }
    try {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(standardizationResponse(
          previous ? 'archivo_anterior.csv' : 'archivo_nuevo.csv',
          previous ? 'anterior' : 'nuevo',
        )),
      })
    } catch {
      // La peticion anterior debe ser abortada al elegir el archivo nuevo.
    }
  })

  await page.goto('/estandarizacion')
  const input = page.locator('input[type="file"]')
  await input.setInputFiles({
    name: 'archivo_anterior.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('Valor\nanterior\n'),
  })
  await expect.poll(() => previousRequestStarted).toBe(true)
  await input.setInputFiles({
    name: 'archivo_nuevo.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('Valor\nnuevo\n'),
  })

  await expect(page.getByText('Dataset activo: archivo_nuevo.csv')).toBeVisible()
  await expect(page.getByRole('table').getByText('archivo_nuevo.csv', { exact: true })).toBeVisible()
  await page.waitForTimeout(1_200)
  await expect(page.getByText('Dataset activo: archivo_nuevo.csv')).toBeVisible()
  await expect(page.getByText('archivo_anterior.csv', { exact: true })).toHaveCount(0)
})

test('Fase 17 procesa, combina, relaciona y exporta un libro multihoja', async ({ page }, testInfo) => {
  const workbook = testInfo.outputPath('ventas_multihoja.xlsx')
  createWorkbook(workbook)

  await page.goto('/estandarizacion')
    const chooserPromise = page.waitForEvent('filechooser')
    await page.getByRole('button', { name: /Subir archivo/ }).click()
    const chooser = await chooserPromise
    await chooser.setFiles(workbook)

    await expect(page.getByText(/Dataset activo:/)).toBeVisible({ timeout: 60_000 })
    await expect(page.getByText('Todas las hojas', { exact: true })).toBeVisible()
    await expect(page.getByText('3 de 3 hojas seleccionadas')).toHaveCount(0)
    await expect(page.getByText(/estructuras distintas/i)).toHaveCount(0)
    const selectedSheets = page.getByRole('checkbox', { name: /Procesar hoja/ })
    await expect(selectedSheets).toHaveCount(3)
    for (let index = 0; index < 3; index += 1) {
      await expect(selectedSheets.nth(index)).toBeChecked()
    }
    await expect(page.getByText('Estandarizada', { exact: true })).toHaveCount(3, { timeout: 90_000 })
    await expect(page.getByRole('button', { name: /preparación|Preparar hojas/ })).toHaveCount(0)
    await expect(page.getByText('Enero', { exact: true })).toHaveCount(1)
    await expect(page.getByText('Febrero', { exact: true })).toHaveCount(1)
    await expect(page.getByText('Productos', { exact: true })).toHaveCount(1)

    await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
    await expect(page.getByText('Problemas detectados')).toBeVisible({ timeout: 90_000 })
    await expect(page.getByText(/Qué se eliminará \/ corregirá/)).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Reglas automáticas (no eliminan filas)' })).toBeVisible()
    await expect(page.getByText('3 pendientes', { exact: true })).toBeVisible()
    await page.waitForTimeout(1_000)
    await expect(page.getByText('3 pendientes', { exact: true })).toBeVisible()
    const cleanAllButton = page.getByRole('button', { name: 'Limpiar datos', exact: true })
    await expect(cleanAllButton).toBeEnabled()
    await cleanAllButton.click()
    await expect(page.getByText(/Todas las hojas están limpias/)).toBeVisible({ timeout: 90_000 })
    await expect(page.getByText('3 limpias', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: /Descargar libro completo/ })).toBeVisible({ timeout: 90_000 })
    const downloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: /Descargar libro completo/ }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toMatch(/multihoja_limpio\.xlsx$/)

    await page.setViewportSize({ width: 1600, height: 1000 })
    await page.getByRole('link', { name: /Resumen/ }).first().click()
    await expect(page.getByText('Datos que estas analizando')).toBeVisible({ timeout: 60_000 })
    await page.getByRole('button', { name: /Solo apilar ventas/ }).click()
    await expect(page.getByText(/hoja_origen/)).toBeVisible()
    await expect(page.getByText('Evolución de Ingresos')).toBeVisible({ timeout: 90_000 })
    const compactFlow = page.getByTestId('summary-compact-flow')
    await expect(compactFlow).toBeVisible()
    const compactLayout = await compactFlow.evaluate((element) => {
      const children = Array.from(element.children) as HTMLElement[]
      return {
        columnCount: getComputedStyle(element).columnCount,
        flowHeight: element.getBoundingClientRect().height,
        totalCardHeight: children.reduce(
          (total, child) => total + child.getBoundingClientRect().height,
          0,
        ),
        avoidsSplits: children.every(
          (child) => getComputedStyle(child).breakInside === 'avoid',
        ),
        cardCount: children.length,
      }
    })
    expect(compactLayout.columnCount).toBe('2')
    expect(compactLayout.cardCount).toBeGreaterThan(1)
    expect(compactLayout.avoidsSplits).toBe(true)
    expect(compactLayout.flowHeight).toBeLessThan(compactLayout.totalCardHeight - 20)

    await page.getByRole('button', { name: /Ventas \+ costos/ }).click()
    await expect(page.getByText('Ventas + costos activo')).toBeVisible({ timeout: 90_000 })
    await expect(page.getByText(/2 hojas de ventas combinadas/)).toBeVisible()
    await expect(page.getByRole('button', { name: /Apilar y relacionar/ })).toHaveCount(0)
    await page.getByRole('checkbox', { name: 'Enero' }).uncheck()
    await expect(page.getByText(/Febrero ↔ Productos/)).toBeVisible({ timeout: 90_000 })
    await expect(page.getByText('Ventas + costos activo')).toBeVisible()
    await page.getByRole('checkbox', { name: 'Enero' }).check()
    await expect(page.getByText(/2 hojas de ventas combinadas/)).toBeVisible({ timeout: 90_000 })
    await expect(page.getByRole('button', { name: /Apilar y relacionar/ })).toHaveCount(0)
    await expect(page.getByText('Cobertura de Costos')).toBeVisible({ timeout: 90_000 })
    await expect(page.getByText('Costo Conocido')).toBeVisible()
    await expect(page.getByText('$17.400', { exact: true })).toBeVisible()
    await page.getByRole('link', { name: /Explorar datos/ }).first().click()
    await expect(page.getByText('Datos que estas analizando')).toBeVisible()
    await expect(page.getByText('Explorar · confiabilidad del margen')).toBeVisible()
    await expect(page.getByText('¿Qué tan explicable es la utilidad?')).toBeVisible()
})

test('permite revisar una limpieza terminada y volver a limpiar sin subir el archivo', async ({ page }, testInfo) => {
  const workbook = testInfo.outputPath('ventas_con_duplicado.xlsx')
  createDuplicateWorkbook(workbook)

  await page.goto('/estandarizacion')
  const chooserPromise = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /Subir archivo/ }).click()
  const chooser = await chooserPromise
  await chooser.setFiles(workbook)
  await expect(page.getByText(/Dataset activo:/)).toBeVisible({ timeout: 60_000 })
  await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
  await expect(page.getByText('Problemas detectados')).toBeVisible({ timeout: 90_000 })
  await page.getByRole('button', { name: 'Limpiar datos', exact: true }).click()
  await expect(page.getByText(/Todas las hojas están limpias/)).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText(/1 detectados/)).toBeVisible()
  await expect(page.getByText(/0 eliminados/)).toBeVisible()

  await page.getByRole('link', { name: /Resumen/ }).first().click()
  await expect(page.getByText(/Se detectaron 1 duplicados exactos/)).toBeVisible({ timeout: 90_000 })
  await page.getByRole('link', { name: 'Ver detalle y ajustar' }).click()
  await expect(page).toHaveURL(/\/limpieza\?revision=1$/)
  await expect(page.getByText('Revisando el diagnóstico original')).toBeVisible()
  await expect(page.getByText('Problemas detectados')).toBeVisible({ timeout: 90_000 })
  await page.getByRole('button', { name: /Eliminar duplicados exactos \(1\)/ }).click()
  await page.getByRole('button', { name: 'Incluir en la próxima limpieza' }).click()
  await expect(page.getByRole('button', { name: /Conservar duplicados en la próxima limpieza/ })).toBeVisible()
  await page.getByRole('button', { name: 'Volver a limpiar', exact: true }).click()

  await expect(page.getByText(/Todas las hojas están limpias/)).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText(/1 eliminados/)).toBeVisible()
  await page.getByRole('button', { name: 'Ver detalle y ajustar' }).click()
  await expect(page.getByText('Revisando el diagnóstico original')).toBeVisible()
  await page.getByRole('button', { name: 'Volver al resultado limpio' }).click()
  await expect(page.getByText(/1 eliminados/)).toBeVisible()
})

test('limpia todas las hojas y elimina duplicados en lote sin bloquear catalogos de costos', async ({ page }, testInfo) => {
  const workbook = testInfo.outputPath('duplicados_por_lote.xlsx')
  createBatchDuplicateWorkbook(workbook)

  await page.goto('/estandarizacion')
  const chooserPromise = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /Subir archivo/ }).click()
  const chooser = await chooserPromise
  await chooser.setFiles(workbook)
  await expect(page.getByText(/Dataset activo:/)).toBeVisible({ timeout: 60_000 })
  await expect(page.getByText('Estandarizada', { exact: true })).toHaveCount(3, { timeout: 90_000 })

  await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
  await expect(page.getByText('Problemas detectados')).toBeVisible({ timeout: 90_000 })
  await page.getByLabel('Hoja mostrada').selectOption('Costos_Productos')
  await expect(page.getByText('Hoja mostrada: Costos_Productos').first()).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText('¿En qué columna está el total vendido?')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Completar limpieza de todas/ })).toHaveCount(0)
  await page.getByRole('button', { name: 'Limpiar datos', exact: true }).click()
  await expect(page.getByText('3 limpias', { exact: true })).toBeVisible({ timeout: 90_000 })

  const selectiveButtons = page.getByRole('button', { name: /Eliminar 1 de esta hoja/ })
  await expect(selectiveButtons).toHaveCount(2)
  await selectiveButtons.first().click()
  await expect(page.getByRole('heading', { name: /¿Eliminar 1 duplicados exactos de/ })).toBeVisible()
  await page.getByRole('button', { name: 'Eliminar duplicados exactos' }).click()
  await expect(page.getByRole('button', { name: /Eliminar duplicados de todas \(1\)/ })).toBeVisible({ timeout: 90_000 })

  await page.getByRole('button', { name: /Eliminar duplicados de todas \(1\)/ }).click()
  await expect(page.getByRole('heading', { name: /¿Eliminar 1 duplicados en 1 hoja/ })).toBeVisible()
  await page.getByRole('button', { name: 'Eliminar en todas' }).click()
  await expect(page.getByText('3 limpias', { exact: true })).toBeVisible({ timeout: 90_000 })
  await expect(page.getByRole('button', { name: /Eliminar duplicados de todas/ })).toHaveCount(0)
})

test('Resumen prioriza y Explorar profundiza en una hoja operacional', async ({ page }, testInfo) => {
  const workbook = testInfo.outputPath('proveedores.xlsx')
  createProviderWorkbook(workbook)

  await page.goto('/estandarizacion')
  const chooserPromise = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /Subir archivo/ }).click()
  const chooser = await chooserPromise
  await chooser.setFiles(workbook)
  await expect(page.getByText(/Dataset activo:/)).toBeVisible({ timeout: 60_000 })

  await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
  await expect(page.getByText('Problemas detectados')).toBeVisible({ timeout: 90_000 })
  await page.getByRole('button', { name: 'Limpiar datos', exact: true }).click()
  await expect(page.getByText(/Todas las hojas están limpias/)).toBeVisible({ timeout: 90_000 })

  await page.getByRole('link', { name: /Resumen/ }).first().click()
  await expect(page.getByText('Red de proveedores')).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText('Resumen · decidir y priorizar')).toBeVisible()
  await expect(page.getByText('Diccionario rápido de la hoja')).toHaveCount(0)

  await page.getByRole('link', { name: /Explorar datos/ }).first().click()
  await expect(page.getByText('Explorar · entender causas')).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText('Diccionario rápido de la hoja')).toBeVisible()
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
    await expect(page.getByText('Problemas detectados')).toBeVisible({ timeout: 90_000 })
    await page.getByRole('button', { name: 'Limpiar datos', exact: true }).click()
    await expect(page.getByText(/Todas las hojas están limpias/)).toBeVisible({ timeout: 90_000 })
    await page.getByRole('link', { name: /Resumen/ }).first().click()
    await page.getByRole('button', { name: /Ventas \+ costos/ }).click()
    await expect(page.getByText(/repite identificadores y podría multiplicar ventas/i)).toBeVisible({ timeout: 90_000 })
    await expect(page.getByRole('button', { name: /Apilar y relacionar/ })).toHaveCount(0)
})
