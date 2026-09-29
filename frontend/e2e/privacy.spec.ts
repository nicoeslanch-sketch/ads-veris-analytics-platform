import { test, expect } from '@playwright/test'

for (const width of [390, 1280]) {
  test(`public policies and rights request fit at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 850 })
    await page.goto('/privacidad')
    await expect(page.getByRole('heading', { name: 'Politica de privacidad' })).toBeVisible()
    await expect(page.getByText('ADS Veris SpA · Version 2026-09-28')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `test-results/privacy-policy-${width}.png`, fullPage: true })
    await page.getByRole('link', { name: 'Licencias', exact: true }).click()
    const notices = await page.request.get('/THIRD_PARTY_NOTICES.txt')
    expect(notices.ok()).toBe(true)
    expect(await notices.text()).toContain('SIL OPEN FONT LICENSE')
    await page.route('**/src/lib/api.ts', route => route.fulfill({ contentType: 'application/javascript', body: `
      let accepted=false; let requests=[];
      export class ApiError extends Error {}
      export async function apiGet() {return {accepted,version:'2026-09-28',requests};}
      export async function apiPostJson(path,body) {
        if(path.includes('acceptance')) {accepted=true; return apiGet();}
        requests=[{id:'synthetic-receipt',kind:body.kind,status:'pending',response:'',created_at:'2026-09-28'}];
        return requests[0];
      }
    ` }))
    await page.goto('/e2e/fixtures/privacy.html')
    await expect(page.getByRole('checkbox', { name: /Acepto las/ })).not.toBeChecked()
    await expect(page.getByRole('button', { name: 'Registrar mi aceptacion' })).toBeDisabled()
    await page.getByRole('combobox').selectOption('erasure')
    const submit = page.getByRole('button', { name: 'Solicitar eliminacion de cuenta y datos' })
    await expect(submit).toBeDisabled()
    await page.getByRole('checkbox', { name: /Solicito eliminar/ }).check()
    await submit.click()
    await expect(page.getByRole('status')).toContainText('Aun no se han eliminado datos')
    await expect(page.getByText('Eliminar mi cuenta y mis datos · Recibida')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `test-results/privacy-request-${width}.png`, fullPage: true })
  })
}

test('signup requires affirmative consent and phone is optional', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: 'Regístrate' }).click()
  await expect(page.getByRole('checkbox', { name: /Acepto las/ })).not.toBeChecked()
  await expect(page.getByRole('button', { name: 'Crear cuenta', exact: true })).toBeDisabled()
  await expect(page.locator('input[type="tel"]')).not.toHaveAttribute('required')
})

test('legacy account must affirm consent but can request erasure without it', async ({ page }) => {
  await page.route('**/src/auth/AuthContext.tsx', route => route.fulfill({ contentType: 'application/javascript', body:
    `export function useAuth(){return {session:{user:{id:'synthetic'}},logout:async()=>{}}}` }))
  await page.route('**/src/lib/api.ts', route => route.fulfill({ contentType: 'application/javascript', body: `
    export class ApiError extends Error {}
    export async function apiGet(){return {accepted:false,version:'2026-09-28',requests:[]}}
    export async function apiPostJson(path){return path.includes('acceptance')
      ? {accepted:true,version:'2026-09-28',requests:[]} : {id:'receipt'}}
  ` }))
  await page.goto('/e2e/fixtures/privacy.html?gate')
  await expect(page.getByText('Espacio de trabajo de prueba')).toHaveCount(0)
  await page.getByRole('combobox').selectOption('erasure')
  await page.getByRole('checkbox', { name: /Solicito eliminar/ }).check()
  await page.getByRole('button', { name: 'Solicitar eliminacion de cuenta y datos' }).click()
  await expect(page.getByRole('status')).toContainText('Solicitud recibida')
  await expect(page.getByRole('checkbox', { name: /Acepto las/ })).not.toBeChecked()
  await page.getByRole('checkbox', { name: /Acepto las/ }).check()
  await page.getByRole('button', { name: 'Registrar mi aceptacion' }).click()
  await expect(page.getByText('Espacio de trabajo de prueba')).toBeVisible()
})
