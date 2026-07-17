import { expect, test } from '@playwright/test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const demoCsv = resolve(here, '../../api/demo/demo_empresa_ficticia.csv')

test('demo ficticia navega sin escrituras y vuelve al estado vacío', async ({ page }) => {
  await page.goto('/')

  const demoButton = page.getByRole('button', { name: 'Ver demo ficticia' })
  await expect(demoButton).toBeVisible()
  await expect(page.getByRole('button', { name: /Probar demo gratuita/ })).toHaveCount(0)

  await demoButton.click()
  await expect(page.getByText('Datos ficticios de ejemplo').first()).toBeVisible()
  await expect(page.getByText('Demo — Comercial Andes SpA')).toBeVisible()
  await expect(page.getByText('Ingresos Totales')).toBeVisible()
  await expect(page.getByText(/último registro disponible el día 15/i)).toBeVisible()

  await page.getByRole('link', { name: /Explorar datos/ }).first().click()
  await expect(page.getByText('Datos ficticios de ejemplo').first()).toBeVisible()
  await expect(page.getByText(/el asistente con IA está desactivado/i)).toBeVisible()
  await expect(page.getByRole('button', { name: /Guardar análisis/ })).toHaveCount(0)

  await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
  await expect(page.getByText('Limpieza de datos — demo')).toBeVisible()
  await expect(page.getByText('Duplicados detectados')).toBeVisible()

  await page.getByRole('link', { name: /Resumen/ }).first().click()
  await page.getByRole('button', { name: 'Salir de la demo' }).click()
  await expect(page.getByText('Aún no hay datos para mostrar')).toBeVisible()
})

test('pipeline real estandariza, limpia y habilita dashboard', async ({ page }) => {
  await page.goto('/estandarizacion')
  const chooserPromise = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: /Subir archivo/ }).click()
  const chooser = await chooserPromise
  await chooser.setFiles(demoCsv)

  await expect(page.getByText(/Dataset activo:/)).toBeVisible({ timeout: 60_000 })
  await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
  const cleanButton = page.getByRole('button', { name: /Limpiar datos/ }).first()
  await expect(cleanButton).toBeEnabled({ timeout: 60_000 })
  await cleanButton.click()

  await page.getByRole('link', { name: /Resumen/ }).first().click()
  await expect(page.getByText('Evolución de Ingresos')).toBeVisible({ timeout: 90_000 })

  await page.getByRole('link', { name: /Explorar datos/ }).first().click()
  await expect(page.getByRole('button', { name: /Guardar análisis/ })).toBeVisible({
    timeout: 60_000,
  })
})

test('registro exige confirmación y controles de contraseña accesibles', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: 'Regístrate' }).click()

  await expect(page.getByText('Confirmar contraseña')).toBeVisible()
  const password = page.getByPlaceholder('Mínimo 8 caracteres, letras y números')
  const confirmation = page.getByPlaceholder('Repite tu contraseña')
  await password.fill('clave1234')
  await confirmation.fill('clave123')
  await expect(page.getByText('Las contraseñas no coinciden.')).toBeVisible()
  await confirmation.fill('clave1234')
  await expect(page.getByText('Las contraseñas coinciden.')).toBeVisible()

  const eyes = page.getByRole('button', { name: 'Mostrar contraseña' })
  await expect(eyes).toHaveCount(2)
  await eyes.first().click()
  await expect(password).toHaveAttribute('type', 'text')
})
