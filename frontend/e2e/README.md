# E2E con Playwright Test

La configuración levanta API y Vite automáticamente, usa rutas relativas al
repositorio y ejecuta Chromium igual que GitHub Actions.

```bash
npm ci
npx playwright install chromium
npm run test:e2e
```

Los artefactos de fallos (trace, captura y video) quedan en `test-results/`.

`fase17_multihoja.spec.ts` genera libros sintéticos en el directorio temporal
del sistema: no usa archivos ni datos reales. Cubre procesamiento secuencial,
limpieza total, exportación, apilado, relación segura y bloqueo many-to-many.
