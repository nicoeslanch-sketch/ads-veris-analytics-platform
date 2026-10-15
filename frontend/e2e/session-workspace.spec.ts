import { expect, test, type Page } from '@playwright/test'

const verified = { enforced: true, has_mfa: true, admin_required: true, verified: true, needs_verification: false }

async function openWorkspace(page: Page) {
  await page.route('**/src/auth/AuthContext.tsx', route => route.fulfill({
    contentType: 'application/javascript',
    body: "export { useAuth, AuthProvider } from '/e2e/fixtures/session-auth.tsx'",
  }))
  await page.route('**/security/session', route => route.fulfill({ json: verified }))
  await page.goto('/e2e/fixtures/session-workspace.html')
  await page.getByRole('button', { name: 'Preparar documento sin guardar' }).click()
  await expect(page.getByText('sin-guardar.csv')).toBeVisible()
  await expect(page.getByText('Limpieza conservada')).toBeVisible()
}

test('session renewal blocks access until verified and preserves unsaved file, cleaning and period', async ({ page }) => {
  await openWorkspace(page)
  let release!: () => void
  const response = new Promise<void>(resolve => { release = resolve })
  await page.route('**/security/session', async route => { await response; await route.fulfill({ json: verified }) })
  await page.getByRole('button', { name: 'Renovar sesion de prueba' }).click()
  await expect(page.getByRole('status')).toContainText('Verificando acceso')
  await expect(page.getByRole('region', { name: 'Documento de prueba' })).toHaveCount(0)
  release()
  await expect(page.getByText('sin-guardar.csv')).toBeVisible()
  await expect(page.getByText('Limpieza conservada')).toBeVisible()
  await expect(page.getByText('2025', { exact: true })).toBeVisible()
  const contents = page.waitForEvent('dialog')
  await page.getByRole('button', { name: 'Comprobar contenido original' }).click()
  const dialog = await contents
  expect(dialog.message()).toBe('private synthetic contents')
  await dialog.dismiss()
})

test('failed renewal verification remains closed and retry recovers the same document', async ({ page }) => {
  await openWorkspace(page)
  await page.route('**/security/session', route => route.fulfill({ status: 503, json: { detail: 'unavailable' } }))
  await page.getByRole('button', { name: 'Renovar sesion de prueba' }).click()
  await expect(page.getByRole('alert')).toContainText('No pudimos verificar')
  await expect(page.getByText('sin-guardar.csv')).toHaveCount(0)
  await page.route('**/security/session', route => route.fulfill({ json: verified }))
  await page.getByRole('button', { name: 'Reintentar', exact: true }).click()
  await expect(page.getByText('sin-guardar.csv')).toBeVisible()
  await expect(page.getByText('Limpieza conservada')).toBeVisible()
})

test('changing account or signing out clears the previous account document', async ({ page }) => {
  await openWorkspace(page)
  await page.getByRole('button', { name: 'Cambiar cuenta de prueba' }).click()
  await expect(page.getByText('Sin archivo', { exact: true })).toBeVisible()
  await expect(page.getByText('sin-guardar.csv')).toHaveCount(0)
  await expect(page.getByText('Sin limpieza', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Preparar documento sin guardar' }).click()
  await expect(page.getByText('sin-guardar.csv')).toBeVisible()
  await page.getByRole('button', { name: 'Salir de prueba' }).click()
  await expect(page.getByText('Sin archivo', { exact: true })).toBeVisible()
  await expect(page.getByText('sin-guardar.csv')).toHaveCount(0)
})

test('renewed session requiring MFA never exposes the preserved document', async ({ page }) => {
  await openWorkspace(page)
  await page.route('**/security/session', route => route.fulfill({
    json: { ...verified, verified: false, needs_verification: true },
  }))
  await page.getByRole('button', { name: 'Renovar sesion de prueba' }).click()
  await expect(page.getByText('La cuenta administradora requiere', { exact: false })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Documento de prueba' })).toHaveCount(0)
  await expect(page.getByText('sin-guardar.csv')).toHaveCount(0)
})
