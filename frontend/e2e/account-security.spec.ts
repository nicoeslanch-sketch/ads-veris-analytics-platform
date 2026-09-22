import { test, expect, type Page } from '@playwright/test'

async function mocks(page: Page, { loadError = false, sessionError = false, required = true } = {}) {
  await page.route('**/src/lib/supabase.ts', route => route.fulfill({ contentType: 'application/javascript', body: `
    let verified = false;
    const factor = { id: 'synthetic-factor', friendly_name: 'Dispositivo de prueba', factor_type: 'totp', status: 'verified' };
    export const supabase = { auth: { mfa: {
      async listFactors() { return ${loadError} ? { error: { message: 'secret diagnostic' } } : { data: { all: verified ? [factor] : [], totp: verified ? [factor] : [] } }; },
      async enroll() { return { data: { id: factor.id, totp: { secret: 'SYNTHETICKEY', qr_code: 'data:image/svg+xml;utf-8,<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect x="20" y="20" width="160" height="160" fill="#000"/></svg>' } } }; },
      async challengeAndVerify({code}) { if (code !== '123456') return { error: { code: 'mfa_verification_failed' } }; verified = true; return { data: {} }; },
      async unenroll() { verified = false; return { data: {} }; }
    }, async refreshSession() { return { data: {} }; } } };
  ` }))
  await page.route('**/src/auth/AuthContext.tsx', route => route.fulfill({ contentType: 'application/javascript', body: `
    export function useAuth() { return { session: {user:{id:'synthetic'},access_token:'synthetic'},recoveryMode:false,logout:async()=>{} }; }
  ` }))
  await page.route('**/src/lib/api.ts', route => route.fulfill({ contentType: 'application/javascript', body: `
    export async function apiGet() {
      if (${sessionError}) throw new Error('private diagnostic');
      return { enforced:true,has_mfa:false,admin_required:${required},verified:false,needs_verification:${required} };
    }
  ` }))
}

test('MFA: failed lookup cannot start blind enrollment', async ({ page }) => {
  await mocks(page, { loadError: true })
  await page.goto('/e2e/fixtures/security.html')
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Configurar autenticador', exact: true })).toBeDisabled()
  await expect(page.getByText('Sin autenticador configurado.')).toHaveCount(0)
  await expect(page.getByText('secret diagnostic')).toHaveCount(0)
})

test('MFA: explicit enrollment, wrong code, verify, last admin factor protected', async ({ page }) => {
  await mocks(page)
  await page.goto('/e2e/fixtures/security.html')
  await expect(page.getByRole('img', { name: 'QR privado' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Configurar autenticador', exact: true }).click()
  await expect(page.getByRole('img', { name: 'QR privado' })).toBeVisible()
  await expect(page.getByText('SYNTHETICKEY')).toHaveCount(0)
  await page.getByLabel('Codigo de seis digitos').fill('000000')
  await page.getByRole('button', { name: 'Verificar codigo' }).click()
  await expect(page.getByRole('alert')).toContainText('incorrecto')
  await expect(page.getByLabel('Codigo de seis digitos')).toHaveValue('')
  await page.getByLabel('Codigo de seis digitos').fill('123456')
  await page.getByRole('button', { name: 'Verificar codigo' }).click()
  await expect(page.getByText('Segundo factor verificado.')).toBeVisible()
  await expect(page.getByRole('img', { name: 'QR privado' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Retirar Dispositivo de prueba' })).toBeDisabled()
})

for (const width of [390, 1280]) {
  test(`MFA gate blocks private UI and fits at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 })
    await mocks(page)
    await page.goto('/e2e/fixtures/security.html?gate')
    await expect(page.getByText('La cuenta administradora requiere')).toBeVisible()
    await expect(page.getByText('Datos privados de prueba')).toHaveCount(0)
    await page.getByRole('button', { name: 'Configurar autenticador', exact: true }).click()
    await expect(page.getByRole('img', { name: 'QR privado' })).toBeVisible()
    const rendered = await page.getByRole('img', { name: 'QR privado' }).evaluate((img: HTMLImageElement) => {
      const canvas = document.createElement('canvas'); canvas.width = 200; canvas.height = 200
      const ctx = canvas.getContext('2d')!; ctx.drawImage(img, 0, 0)
      return [...ctx.getImageData(100, 100, 1, 1).data]
    })
    expect(rendered).toEqual([0, 0, 0, 255])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `test-results/mfa-${width}.png`, fullPage: true })
  })
}

test('MFA gate fails closed when status is unavailable', async ({ page }) => {
  await mocks(page, { sessionError: true })
  await page.goto('/e2e/fixtures/security.html?gate')
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByText('Datos privados de prueba')).toHaveCount(0)
})

test('MFA gate permits a customer without enrollment', async ({ page }) => {
  await mocks(page, { required: false })
  await page.goto('/e2e/fixtures/security.html?gate')
  await expect(page.getByText('Datos privados de prueba')).toBeVisible()
})
