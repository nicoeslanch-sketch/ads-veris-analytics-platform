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

for (const isAdmin of [false, true]) {
  test(`returning ${isAdmin ? 'administrator' : 'customer'} enters and reloads without a privacy gate`, async ({ page }) => {
    await page.route('**/src/auth/AuthContext.tsx', route => route.fulfill({
      contentType: 'application/javascript', body: `
        const user = {id:'synthetic-returning-user',email:'returning@example.test',user_metadata:{}};
        export function AuthProvider({children}){return children;}
        export function useAuth(){return {session:{user,access_token:'synthetic'},user,
          loading:false,configured:true,recoveryMode:false,logout:async()=>{}};}
        export function translateAuthError(){return 'Error de prueba';}
      `,
    }))
    await page.route('**/src/lib/access.tsx', route => route.fulfill({
      contentType: 'application/javascript', body: `
        export function AccessProvider({children}){return children;}
        export function useAccess(){return {status:'resolved',can:()=>true,refresh:()=>{},
          access:{paid_plan:'basico',plan_display:'Básico',is_admin:${isAdmin},enforcement:true,
            capabilities:[],trial:{active:false,used:true,days_remaining:0}}};}
      `,
    }))
    await page.route('**/security/session', route => route.fulfill({json:{
      enforced:true,has_mfa:false,admin_required:false,verified:true,needs_verification:false,
    }}))
    let privacyReads = 0
    await page.route('**/privacy/account', route => {
      privacyReads++
      return route.fulfill({status:503,json:{detail:'Privacidad temporalmente no disponible'}})
    })
    await page.goto('/')
    const resumen = page.getByRole('link', {name:'Resumen',exact:true})
    await expect(resumen).toBeVisible()
    await expect(page.getByRole('heading', {name:'Tu privacidad en ADS Veris'})).toHaveCount(0)
    await page.getByRole('link', {name:'Explorar datos',exact:true}).click()
    await expect(page).toHaveURL(/\/explorar$/)
    await expect(resumen).toBeVisible()
    await page.reload()
    await expect(resumen).toBeVisible()
    await resumen.click()
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('button', {name:'Enviar solicitud',exact:true})).toHaveCount(0)
    await expect(page.getByRole('link', {name:'Administrar cuentas',exact:true})).toHaveCount(isAdmin ? 1 : 0)
    expect(privacyReads).toBe(0)
  })
}

test('login does not request consent or a privacy request', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByRole('heading', {name:'Inicia sesión'})).toBeVisible()
  await expect(page.getByRole('checkbox', {name:/Acepto las/})).toHaveCount(0)
  await expect(page.getByRole('button', {name:'Enviar solicitud',exact:true})).toHaveCount(0)
})
