/** E2E Fase 14 — demo ficticia, registro reforzado y pipeline real intacto. */
import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'
const results = []
const ok = (name) => { results.push(['✓', name]); console.log('✓', name) }
const fail = (name, extra) => { results.push(['✗', name]); console.log('✗', name, extra ?? '') }

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' })
const page = await browser.newPage()
page.setDefaultTimeout(20000)

try {
  // ── 1. Resumen vacío: botón "Ver demo ficticia" presente ──
  await page.goto(BASE + '/')
  await page.waitForTimeout(2500)
  const demoBtn = page.getByRole('button', { name: 'Ver demo ficticia' })
  if (await demoBtn.count()) ok('Estado vacío de Resumen muestra "Ver demo ficticia"')
  else fail('Botón demo en Resumen vacío')

  // (dev fail-open = plan básico → NO debe ofrecerse la prueba gratuita)
  const trialBtn = page.getByRole('button', { name: /Probar demo gratuita/ })
  if ((await trialBtn.count()) === 0) ok('Con plan activo NO se ofrece la prueba gratuita')
  else fail('Prueba gratuita ofrecida a cuenta con plan')

  // ── 2. Entrar a la demo ──
  await demoBtn.first().click()
  await page.waitForTimeout(1500)
  const banner = page.getByText('Datos ficticios de ejemplo').first()
  if (await banner.count()) ok('Banner persistente "Datos ficticios de ejemplo"')
  else fail('Banner de demo')
  if (await page.getByText('Demo — Comercial Andes SpA').count()) ok('Resumen renderiza la demo (Comercial Andes SpA)')
  else fail('Título demo en Resumen')
  const kpiIngresos = await page.getByText('Ingresos Totales').count()
  if (kpiIngresos) ok('KPIs de la demo visibles')
  else fail('KPIs demo')
  // El mes parcial se identifica con la nota al pie
  if (await page.getByText(/último registro disponible el día 15/).count()) ok('Nota de mes parcial (junio hasta día 15) visible')
  else fail('Nota de mes parcial')

  // ── 3. Explorar en demo (navegación in-app: la demo vive en estado React) ──
  await page.getByRole('link', { name: /Explorar datos/ }).first().click()
  await page.waitForTimeout(2000)
  if (await page.getByText('Datos ficticios de ejemplo').count()) ok('Banner demo persiste en Explorar')
  else fail('Banner demo en Explorar')
  if (await page.getByText(/el asistente con IA está desactivado/i).count()) ok('Explorar demo: IA desactivada (sin llamadas)')
  else fail('Mensaje IA desactivada en Explorar demo')
  // Fase 14b (P0.4): la demo JAMÁS escribe — el botón de guardar no existe
  if ((await page.getByRole('button', { name: /Guardar análisis/ }).count()) === 0)
    ok('Explorar demo: sin botón "Guardar análisis" (cero escrituras)')
  else fail('La demo ofrece guardar análisis')

  // ── 4. Limpieza en demo: resumen read-only ──
  await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
  await page.waitForTimeout(1500)
  if (await page.getByText('Limpieza de datos — demo').count()) ok('Limpieza demo: resumen read-only')
  else fail('Limpieza demo')
  if (await page.getByText('Duplicados detectados').count()) ok('Limpieza demo: problemas reales (duplicados)')
  else fail('Problemas demo')

  // ── 5. Salir de la demo restaura el estado vacío ──
  await page.getByRole('link', { name: /Resumen/ }).first().click()
  await page.waitForTimeout(1200)
  await page.getByRole('button', { name: 'Salir de la demo' }).click()
  await page.waitForTimeout(1200)
  if (await page.getByText('Aún no hay datos para mostrar').count()) ok('Salir de la demo restaura el estado vacío exacto')
  else fail('Salida de demo')

  // ── 6. Pipeline REAL sigue intacto (regresión del refactor de acceso) ──
  await page.goto(BASE + '/estandarizacion')
  await page.waitForTimeout(1500)
  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.getByRole('button', { name: /Subir archivo/ }).click(),
  ])
  await chooser.setFiles('/home/user/ads-veris-analytics-platform/api/demo/demo_empresa_ficticia.csv')
  await page.waitForTimeout(6000)
  if (await page.getByText('Estandarizado').count()) ok('Pipeline real: archivo estandarizado con el gate nuevo')
  else fail('Estandarización real')

  await page.getByRole('link', { name: /Limpieza de datos/ }).first().click()
  await page.waitForTimeout(6000)
  const limpiarBtn = page.getByRole('button', { name: /Limpiar datos/ })
  await limpiarBtn.first().click()
  await page.waitForTimeout(8000)
  await page.getByRole('link', { name: /Resumen/ }).first().click()
  await page.waitForTimeout(6000)
  if (await page.getByText('Evolución de Ingresos').count()) ok('Pipeline real: dashboard con datos propios tras limpieza')
  else fail('Dashboard real')
  // Con datos reales, Explorar SÍ ofrece guardar (contraste con la demo)
  await page.getByRole('link', { name: /Explorar datos/ }).first().click()
  await page.waitForTimeout(3000)
  if (await page.getByRole('button', { name: /Guardar análisis/ }).count()) ok('Explorar real: botón "Guardar análisis" disponible')
  else fail('Botón guardar en Explorar real')
  await page.getByRole('link', { name: /Resumen/ }).first().click()
  await page.waitForTimeout(8000)
  // Con el archivo real (junio parcial) el gráfico también marca el mes
  if (await page.getByText(/último registro disponible el día 15/).count()) ok('Mes parcial marcado también con datos reales')
  else fail('Mes parcial real')

  // ── 7. Registro reforzado: confirmar contraseña + ojo ──
  // (cerrando sesión no hay; vamos directo a /login — en dev sin Supabase el
  // formulario igual renderiza sus validaciones de UX)
  await page.goto(BASE + '/login')
  await page.waitForTimeout(1000)
  await page.getByRole('button', { name: 'Regístrate' }).click()
  await page.waitForTimeout(500)
  if (await page.getByText('Confirmar contraseña').count()) ok('Registro: campo "Confirmar contraseña" presente')
  else fail('Campo confirmar contraseña')
  const passInput = page.getByPlaceholder('Mínimo 8 caracteres, letras y números')
  const confirmInput = page.getByPlaceholder('Repite tu contraseña')
  await passInput.fill('clave1234')
  await confirmInput.fill('clave123')
  await page.waitForTimeout(300)
  if (await page.getByText('Las contraseñas no coinciden.').count()) ok('Aviso aria-live de no coincidencia')
  else fail('Aviso de no coincidencia')
  await confirmInput.fill('clave1234')
  await page.waitForTimeout(300)
  if (await page.getByText('Las contraseñas coinciden.').count()) ok('Tick verde cuando coinciden y cumplen la política')
  else fail('Confirmación verde')
  const eyes = page.getByRole('button', { name: 'Mostrar contraseña' })
  if ((await eyes.count()) >= 2) ok('Ojos con aria-label en ambos campos')
  else fail('Ojos accesibles', `count=${await eyes.count()}`)
  await eyes.first().click()
  const typeNow = await passInput.getAttribute('type')
  if (typeNow === 'text') ok('El ojo alterna mostrar/ocultar sin borrar el valor')
  else fail('Toggle de ojo')
} catch (err) {
  fail('EXCEPCIÓN', err.message)
} finally {
  await browser.close()
}

const failed = results.filter(([s]) => s === '✗').length
console.log(`\n${results.length - failed}/${results.length} OK`)
process.exit(failed ? 1 : 0)
