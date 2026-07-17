# Auditoría crítica e implementación de Fase 16

Base auditada: commit `bc72257b`. La evaluación se hizo contra código y pruebas,
no contra las declaraciones del CHANGELOG.

## Veredicto sobre el análisis recibido

1. **Correcto, pero incompleto.** El loader conservaba los literales, mientras
   la estandarización seguía borrando tokens reservados. Además, los reportes
   mezclaban nulos físicos y placeholders. Fase 16 clasifica el valor según el
   tipo/rol: en texto, `None`, `none`, `nan`, `NaT`, `NA` y `null` son literales;
   en número/fecha pueden ser placeholders semánticos, sin confundirse con un
   nulo físico. Las pruebas recorren CSV y Excel hasta la exportación.
2. **Correcto.** El bloqueo vivía solo en Resumen. Ahora la API no entrega KPIs
   monetarios utilizables y Explorar, Alertas, Reportes, IA y análisis guardados
   quedan bloqueados cuando `moneda_detalle.mixta` es verdadero. Los análisis
   legados sin evidencia de moneda se conservan, pero sus hallazgos se ocultan
   hasta recalcularlos; los nuevos guardan una marca de integridad verificable.
3. **Correcto.** La detección leía 1.000 filas y el flag dependía del texto de
   una advertencia. `CurrencyDetection` incluye dominante, detectadas, conteos,
   desglose por columna y `mixta`; usa todas las filas de montos y costos.
4. **Correcto.** La revisión se asignaba al final y existía una escritura sin
   guardia. La revisión ahora se reserva antes del cálculo y una RPC PostgreSQL
   guarda estado y hoja atómicamente solo si la revisión es más nueva. Restaurar
   valida SHA-256, hash de reglas, hash de mapeo, hoja y versión del motor.
5. **Correcto.** Las dimensiones antes/después no eran comparables y cobertura
   significaba rol presente. Ambas fases usan la misma fórmula y miden fechas,
   números y dimensiones realmente válidos.
6. **Correcto.** Era un script manual con rutas absolutas. Ahora usa
   `@playwright/test`, rutas relativas, servidores administrados y un job CI.
7. **Parcialmente correcto.** El smoke ya probaba endpoints con dos usuarios,
   pero omitía silenciosamente fixtures y no cubría las tablas directamente.
   En staging/CI ahora falla cerrado y verifica RLS/Storage de forma explícita.
8. **Correcto.** “La base quedó completa” describía solo el subconjunto observado.
   La frase se eliminó. Excel incorpora `Auditoria`; CSV produce un ZIP con datos,
   auditoría y manifiesto. Cada transformación registra original, final, regla,
   acción, confianza, confirmación, motor y procedencia.
9. **Correcto.** El snapshot restauraba solo la hoja activa, reiniciaba sesiones
   y tenía un límite incrustado de 512 KB. El esquema v3 separa estado y hojas y
   conserva sesiones, reglas, mapeos, hoja activa, exclusiones y `combineSheets`.

## Migraciones y operación

- `0019_contratacion_basico.sql`: mismo cambio idempotente de Fase 15,
  renumerado porque había dos archivos locales con versión `0017`.
- `0020_restore_state_v3.sql`: tablas de estado/hojas, RLS, secuencia y RPC
  de reserva/escritura atómica.
- No hay variables nuevas de la aplicación. El smoke estricto requiere las
  variables enumeradas en `docs/OPERACION.md`.
- Aplicar 0019 y 0020 primero en staging, ejecutar el smoke con dos usuarios y
  fixtures de propiedad B, comprobar `GET /version` (`0.19.0`, `0020`) y luego
  promover a producción. No se creó ni simuló estado de pago.

## Verificación local real

- Pytest: 323 pruebas aprobadas.
- Vitest: 31 pruebas aprobadas.
- Build TypeScript/Vite: aprobado.
- Playwright Chromium: 3 de 3 aprobadas.
- `npm audit`: 0 vulnerabilidades conocidas después de actualizar Playwright.

El smoke RLS remoto no puede sustituirse con el bypass local: debe ejecutarse en
staging después de aplicar las migraciones y crear las dos fixtures.

## Riesgos residuales

- No hay conversión de divisas ni KPIs separados por moneda: la política segura
  es bloquear hasta que el usuario entregue una moneda compatible.
- La auditoría completa y la exportación siguen construyéndose en memoria; un
  archivo extraordinariamente grande puede elevar el consumo antes de descargar.
- Los snapshots v2 se aceptan como legado, pero deben recalcularse para obtener
  procedencia y estado multihoja v3.
- La cobertura RLS real depende del smoke de staging; las pruebas unitarias y el
  E2E local no prueban políticas del proyecto Supabase desplegado.
