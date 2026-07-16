/** Vitest (Fase 14b) — pruebas de lógica pura del frontend.
 *
 * Entorno node (sin jsdom): cubre los módulos donde un error NO lo detecta
 * el build — la paridad del RUT con el backend, la normalización de planes y
 * la regla transversal de meses parciales. `npm run test`.
 */
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
