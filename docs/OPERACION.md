# Runbook de operación — ADS Veris

Los puntos del plan "todo en 10" que NO viven en el código del repo viven
aquí como checklist operacional. Cada sección dice qué hacer, dónde y cómo
verificarlo. (Los puntos que SÍ son código ya están implementados — ver
CHANGELOG [0.18.0].)

## 1. Entornos (producción / staging / desarrollo)

- **Producción**: Render (API) + Vercel (frontend) + Supabase actuales.
  - Render: `APP_ENV=production` (obligatorio — con esta variable la API se
    NIEGA a arrancar si falta Supabase, si `PLAN_ENFORCEMENT=false` o si
    `DEV_AUTH_BYPASS=true`; el error dice exactamente qué está mal).
- **Staging** (pendiente de crear): proyecto Supabase SEPARADO + servicio
  Render separado + proyecto Vercel separado, con claves PROPIAS y solo
  datos ficticios (sirve `api/demo/demo_empresa_ficticia.csv`). Ejecutar ahí
  las migraciones ANTES que en producción.
- Verificación de identidad tras cada deploy: `GET /version` debe devolver
  el `commit_sha` que quisiste publicar, `engine_version` y la migración
  esperada (`database_migration`). Si no coinciden → el deploy no salió.

## 2. Checklist de release (orden exacto)

1. CI verde (pytest + Vitest + build + job de seguridad).
2. Migraciones nuevas ejecutadas en STAGING y smoke test ahí.
3. Migraciones en producción (Supabase → SQL Editor, en orden).
4. Deploy backend (Render) → `GET /version` coincide con el SHA.
5. Deploy frontend (Vercel).
6. **Smoke test post-deploy** (10 minutos, a mano o guiado):
   - login con cuenta de prueba SIN plan → no puede subir, ve el modal
     comercial, puede activar trial con RUT de prueba;
   - cuenta con trial ACTIVO → sube y limpia un archivo chico, dashboard OK,
     panel IA muestra el mensaje "disponible desde el Plan Básico";
   - cuenta con trial VENCIDO → bloqueada para procesar, Historial visible;
   - cuenta Básico → pipeline completo + IA responde;
   - cuenta admin → panel Administrar cuentas.
7. Si algo falla → rollback: Render/Vercel permiten redeploy del build
   anterior en un clic; las migraciones de este repo son aditivas (no
   destruyen columnas), así que el código anterior sigue funcionando.

## 3. Seguridad operacional

- **Administración**: una vez confirmado `profiles.is_admin = true` en la
  cuenta administradora, vaciar `ADMIN_EMAIL` en Render (la variable es solo
  bootstrap; mantenerla convierte un correo en credencial permanente).
  Activar **MFA** en esa cuenta (Supabase → Authentication → MFA) y en los
  paneles de Render/Vercel/GitHub.
- **Protección de `main`** (GitHub → Settings → Branches): pull request
  obligatorio, checks `backend`, `frontend` y `seguridad` requeridos, sin
  push directo.
- **Escaneo de secretos**: activar GitHub → Security → Secret scanning +
  Push protection (gratis en repos privados con Advanced Security, o usar
  gitleaks localmente antes de subir).
- **Rotación de claves**: si una clave service_role/API se expone → Supabase
  → Settings → API → regenerar; actualizar Render; verificar `GET /health`.
  Anthropic: revocar y crear en console.anthropic.com.
- **Aislamiento entre clientes**: correr `python api/scripts/smoke_rls.py`
  (ver instrucciones dentro) con dos cuentas de prueba tras cada cambio de
  RLS o migración — verifica que A no puede leer/restaurar/usar nada de B.

## 4. Backups y restauración (probar, no solo activar)

- Supabase → Database → Backups: verificar que los backups diarios están
  activos (plan Pro) y **hacer un simulacro trimestral**: restaurar a un
  proyecto temporal, correr `select count(*) from datasets;` y abrir un
  archivo de Storage. Documentar fecha y resultado aquí:
  - [ ] Último simulacro: ____-__-__ · resultado: ______
- Guardar en un gestor de secretos (no en el repo): variables de Render,
  variables de Vercel, claves Supabase y Anthropic.

## 5. Observabilidad (mínimo viable)

- Render: activar alertas de deploy fallido y de reinicios; revisar memoria.
- Supabase: Reports → API/database errors semanal.
- Logs de la API: ya son estructurados por línea con prefijos (`[quota]`,
  `[trial]`, `[ai]`, `[access]`, `[CORS]`) y JAMÁS incluyen tokens, RUT
  completos ni contenido de archivos — mantener esa regla en todo log nuevo.
- Siguiente paso recomendado (no implementado): Sentry para frontend y
  backend con el `commit_sha` de `/version` como release.

## 6. Pendientes de producto documentados (decisión consciente)

- **Modelo `subscriptions`** (estado de pago/vencimiento/renovación):
  se implementa JUNTO con la pasarela de pago — hoy el plan en `profiles` +
  `addon_requests` con identidad de facturación cubre la operación manual.
- **Ledger de transformaciones por celda + export auditable completo**:
  el resumen por regla ya existe (cambios, fusiones, avisos, auditoría de
  mojibake); el ledger fila-a-fila multiplica memoria en archivos grandes y
  se abordará con streaming/muestreo en una fase dedicada.
- **Restauración multihoja completa** (todas las sesiones por hoja +
  combinación): el snapshot v2 restaura la sesión principal; ampliarlo
  requiere rediseñar el tamaño del snapshot (hoy acotado a 512 KB).
- **KPIs por moneda / conversión declarada**: hoy las monedas mixtas
  BLOQUEAN los KPIs (jamás una cifra inválida); separar por moneda es la
  siguiente iteración.
- **Rate limiting compartido multi-instancia** (Postgres/Redis): necesario
  recién al escalar horizontalmente la API.
