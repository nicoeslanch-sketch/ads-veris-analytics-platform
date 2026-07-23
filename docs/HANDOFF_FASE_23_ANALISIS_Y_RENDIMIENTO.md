# Continuidad: analisis empresarial y rendimiento multihoja

Fecha: 2026-07-22

## Estado base

- Rama: `main` (trabajo directo, sin PR).
- Ultimo commit remoto antes de este cierre: `10010e2dc82a515275c3a3fe8c770e0ffc94d430`.
- Motor: `0.23.0`.
- Ultima migracion: `0021`. No se creo ni ejecuto ninguna migracion.
- Libro principal de auditoria:
  `C:\Users\NICOLAS-PC\Downloads\Prueba_PYME_Desafiante_Multihoja_ADS_VerIs_2026.xlsx`.
- Libro limpio de referencia:
  `C:\Users\NICOLAS-PC\Downloads\Prueba_PYME_Desafiante_Multihoja_ADS_VerIs_2026_limpio.xlsx`.

## Trabajo ya integrado anteriormente

El commit `1e94b154c5e5b4d28a2ae0b69a7704450ef3b375` agrego el motor empresarial
seguro, auditoria de formulas/referencias, costos historicos con fallback actual
marcado como estimacion, KPIs y decisiones, separacion visual entre Resumen y
Explorar, analisis por tipo de hoja, batch de estandarizacion/limpieza,
restauracion versionada y exportacion auditada acelerada.

El commit `10010e2dc82a515275c3a3fe8c770e0ffc94d430` elimino la reapertura del XLSX
por cada hoja. Render, Vercel y CI quedaron verdes para ese SHA antes de iniciar
el ajuste actual.

## Ajuste actual incluido en el siguiente commit

1. `/sheets/relationships` procesa el alcance empresarial con una sola apertura
   del libro y devuelve tambien `analysis_scope` y `metrics` cuando encuentra
   una relacion de costos segura.
2. El frontend reutiliza esas metricas al activar `Vision del negocio`; ya no
   hace una segunda llamada pesada inmediatamente despues.
3. La limpieza multihoja precalienta relacion + metricas en segundo plano usando
   los frames que ya estan en memoria, sin retrasar la respuesta de `Limpiar datos`.
4. Cache LRU de analisis aislada por usuario, SHA del archivo, dataset, version
   del motor, manifiesto efectivo, reglas, mapeo, revision, alcance y periodo.
5. Peticiones identicas simultaneas comparten un unico calculo mediante una
   barrera `inflight`; una revision distinta nunca reutiliza el resultado viejo.
6. `status` y `error` visuales no invalidan la cache, porque no cambian valores;
   reglas, mapeo, alcance, duplicados y revision si la invalidan.

## Mediciones reproducibles

Libro real de 16 hojas, ejecucion local fria:

- pipeline anterior relacion + metricas: aproximadamente `34,2 s`;
- flujo combinado actual: aproximadamente `29,1 s`;
- repeticion identica desde cache: aproximadamente `0,009 s`;
- perfil frio: lectura XLSX `10,3 s`, procesamiento de hojas `13,2 s`,
  relaciones + construccion + metricas + analisis empresarial `7,0 s`.

Se probo paralelizar hojas y se retiro: empeoro a `30,8 s`, por lo que no forma
parte del codigo final.

## Verificaciones ya ejecutadas sobre el estado actual

- Backend completo: `466 passed`.
- Frontend Vitest: `69 passed`.
- TypeScript + Vite production build: aprobado.
- `git diff --check`: aprobado; solo avisos normales LF/CRLF de Windows.
- Pruebas nuevas cubren una sola apertura, metricas precalculadas, cache por
  revision/usuario, deduplicacion de solicitudes concurrentes y precalentamiento.

## Produccion comprobada antes del ultimo ajuste

Con la sesion autenticada y el SHA `10010e2...`:

- Estandarizacion restauro el libro exacto y mostro las 16 hojas limpias.
- Limpieza restauro `16 seleccionadas / 16 limpias / 0 pendientes` en `3,6 s`.
- La vista empresarial calculo ventas verificables, costos, utilidad, margen,
  gastos, cobranza, inventario, metas, cobertura y advertencias correctamente.
- El primer calculo empresarial en Render aun tomo unos `112 s`; ese hallazgo
  motivo el flujo combinado y el precalentamiento de este commit.

## Lo unico que queda por hacer al retomar

1. Confirmar que GitHub Actions del nuevo SHA termino verde (API, frontend,
   seguridad y E2E).
2. Confirmar Vercel `success` y que Render `/version` reporta el nuevo SHA,
   `engine_version=0.23.0`, `database_migration=0021`, `environment=production`.
3. En la sesion autenticada, limpiar o reutilizar el libro principal, esperar
   unos segundos en Limpieza y abrir `Resumen > Vision del negocio`.
4. Medir primera apertura y segunda apertura. La segunda debe reutilizar cache;
   tras una limpieza reciente, la primera tambien deberia encontrar el analisis
   precalentado. Registrar el tiempo real de Render.
5. Verificar Resumen y Explorar, cambiar a una hoja individual y volver a Vision
   del negocio; comprobar que no recalcula ni mezcla revisiones.
6. Si Render sigue lento solo despues de dormir/reiniciar, el siguiente paso
   correcto es persistir un artefacto limpio versionado en Storage. No ocultar
   validaciones ni simplificar el motor; eso requerira diseno y pruebas antes de
   implementarlo.

No hay cambios de Supabase pendientes para este trabajo.
