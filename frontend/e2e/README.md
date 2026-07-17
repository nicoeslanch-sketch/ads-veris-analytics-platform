# E2E de la plataforma (Playwright)

Prerrequisitos (no viven en package.json para no engordar `npm ci` del CI):

```bash
npm i -D playwright        # una vez, local
# API en modo dev:
cd ../api && DEV_AUTH_BYPASS=true SUPABASE_URL= SUPABASE_SERVICE_ROLE_KEY= \
  SUPABASE_JWT_SECRET= python -m uvicorn app.main:app --port 8000
# Frontend:
cd ../frontend && npm run dev
# Correr:
npm run test:e2e
```

Cubre: demo ficticia completa (entrar/navegar/salir, IA desactivada, cero
escrituras), pipeline real con las puertas comerciales, mes parcial marcado,
y el registro reforzado (confirmación, aria-live, ojos accesibles).
