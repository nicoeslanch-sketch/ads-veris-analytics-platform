import { test, expect, type Page } from '@playwright/test'

async function setup(page: Page, failure = false) {
  await page.route('**/src/lib/supabase.ts', route => route.fulfill({ contentType: 'application/javascript', body: `
    export const supabaseConfigured = true;
    window.__signupCalls = []; window.__resendCalls = [];
    export const supabase = { auth: {
      onAuthStateChange() { return {data:{subscription:{unsubscribe(){}}}}; },
      async getSession() { return {data:{session:null}}; },
      async signUp(input) { window.__signupCalls.push(input); return {data:{session:null}, error:null}; },
      async signInWithPassword() { if (${failure}) throw Error('private network detail'); return {error:{message:'Email not confirmed'}}; },
      async resetPasswordForEmail() { throw Error('private network detail'); },
      async resend(input) { window.__resendCalls.push(input); if (${failure}) throw Error('private network detail'); return {error:null}; }
    }};
  ` }))
  await page.goto('/e2e/fixtures/signup.html')
}

test('new signup requires consent and explains confirmation without exposing a session', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await setup(page)
  await page.getByRole('button', { name: 'Regístrate' }).click()
  await page.getByPlaceholder('Ej: Ítalo Alonso').fill('Prueba local')
  await page.getByPlaceholder('Ej: Comercial del Sur SpA').fill('Empresa sintetica')
  await page.getByPlaceholder('tucorreo@empresa.cl').fill('synthetic@example.invalid')
  await page.getByPlaceholder('Mínimo 8 caracteres, letras y números').fill('SyntheticOnly123')
  await page.getByPlaceholder('Repite tu contraseña').fill('SyntheticOnly123')
  await expect(page.getByRole('button', { name: 'Crear cuenta', exact: true })).toBeDisabled()
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Crear cuenta', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('abre el enlace de confirmación')
  await expect(page.getByRole('button', { name: /Reenviar confirmación/ })).toBeDisabled()
  await expect(page.getByPlaceholder('Tu contraseña')).toHaveValue('')
  await expect(page.getByText('Authenticated test view')).toHaveCount(0)
  expect(await page.evaluate(() => (window as any).__signupCalls[0].options.data.service_data_consent)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/signup-confirmation-390.png', fullPage: true })
})

test('unconfirmed login offers signup resend with cooldown and a neutral acknowledgement', async ({ page }) => {
  await setup(page)
  await page.getByPlaceholder('tucorreo@empresa.cl').fill('synthetic@example.invalid')
  await page.getByPlaceholder('Tu contraseña').fill('SyntheticOnly123')
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click()
  await page.getByRole('button', { name: 'Reenviar confirmación', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Si hay una cuenta pendiente')
  await expect(page.getByRole('button', { name: /Reenviar confirmación/ })).toBeDisabled()
  expect(await page.evaluate(() => (window as any).__resendCalls)).toEqual([{type:'signup',email:'synthetic@example.invalid'}])
  await expect(page.getByText('Authenticated test view')).toHaveCount(0)
})

test('network failure on login or recovery releases controls without revealing diagnostics', async ({ page }) => {
  await setup(page, true)
  await page.getByPlaceholder('tucorreo@empresa.cl').fill('synthetic@example.invalid')
  await page.getByPlaceholder('Tu contraseña').fill('SyntheticOnly123')
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click()
  await expect(page.getByText('No pudimos conectar con el servicio de acceso. Vuelve a intentarlo.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Ingresar', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '¿Olvidaste tu contraseña?' }).click()
  await expect(page.getByText('No pudimos conectar con el servicio de correo. Vuelve a intentarlo.')).toBeVisible()
  await expect(page.getByRole('button', { name: '¿Olvidaste tu contraseña?' })).toBeEnabled()
  await expect(page.getByText('private network detail')).toHaveCount(0)
})
