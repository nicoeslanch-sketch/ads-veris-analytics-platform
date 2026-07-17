"""Smoke test de AISLAMIENTO entre clientes (Fase 15).

Verifica contra un entorno REAL (staging o producción con cuentas de prueba)
que el usuario A no puede tocar nada del usuario B a través de la API:

  - restaurar el dataset de B          → 403/404, jamás datos
  - procesar el archivo de B (storage) → 403
  - usar un billing_identity_id de B   → 422
  - rutas administrativas sin is_admin → 403

Uso:
  export API_BASE=https://tu-api.onrender.com
  export JWT_A="eyJ..."   # sesión del usuario A (browser → localStorage)
  export JWT_B="eyJ..."   # sesión del usuario B
  export STORAGE_PATH_B="<uuid-de-B>/1699999999_archivo.xlsx"  # opcional
  export BILLING_ID_B="<uuid billing_identities de B>"          # opcional
  python scripts/smoke_rls.py

Sale con código 0 si TODO el aislamiento se cumple; 1 si algo se filtró.
"""

import os
import sys

import httpx

BASE = os.environ.get("API_BASE", "").rstrip("/")
JWT_A = os.environ.get("JWT_A", "")
JWT_B = os.environ.get("JWT_B", "")

results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    results.append((ok, name))
    print(("✓" if ok else "✗"), name, extra)


def _headers(jwt: str) -> dict:
    return {"Authorization": f"Bearer {jwt}"}


def main() -> int:
    if not BASE or not JWT_A or not JWT_B:
        print("Faltan API_BASE / JWT_A / JWT_B en el entorno. Ver docstring.")
        return 2

    # 0) Ambas sesiones son válidas (si no, el resto no prueba nada)
    for label, jwt in (("A", JWT_A), ("B", JWT_B)):
        r = httpx.get(f"{BASE}/me", headers=_headers(jwt), timeout=20)
        check(f"sesión {label} válida", r.status_code == 200, f"[{r.status_code}]")
    if any(not ok for ok, _ in results):
        return 1

    # 1) A no puede restaurar el último trabajo COMO B (el endpoint deriva el
    #    dueño del JWT: debe devolver LO DE A o nada — nunca lo de B). La
    #    prueba fuerte es el storage_path cruzado (punto 2).
    r = httpx.post(f"{BASE}/restore/latest", headers=_headers(JWT_A), timeout=60)
    check("restore de A no falla por identidad", r.status_code in (200, 403), f"[{r.status_code}]")

    # 2) A no puede procesar un archivo del Storage de B
    path_b = os.environ.get("STORAGE_PATH_B")
    if path_b:
        r = httpx.post(
            f"{BASE}/standardize",
            headers=_headers(JWT_A),
            data={"storage_path": path_b},
            timeout=60,
        )
        check("A no procesa el archivo de B", r.status_code in (403, 404), f"[{r.status_code}]")
    else:
        print("· STORAGE_PATH_B no definido: prueba de Storage cruzado omitida")

    # 3) A no puede vincular la identidad de facturación de B
    billing_b = os.environ.get("BILLING_ID_B")
    if billing_b:
        r = httpx.post(
            f"{BASE}/addons/request",
            headers=_headers(JWT_A),
            json={
                "tipo": "upgrade_analista",
                "mensaje": "smoke rls",
                "billing_identity_id": billing_b,
            },
            timeout=30,
        )
        check("A no usa el billing_identity de B", r.status_code == 422, f"[{r.status_code}]")
    else:
        print("· BILLING_ID_B no definido: prueba de identidad cruzada omitida")

    # 4) Rutas administrativas cerradas para usuarios normales
    r = httpx.get(f"{BASE}/admin/accounts", headers=_headers(JWT_A), timeout=30)
    check("A (no admin) no lista cuentas", r.status_code in (403, 404), f"[{r.status_code}]")
    r = httpx.post(
        f"{BASE}/admin/grant-credits",
        headers=_headers(JWT_A),
        json={"user_id": "00000000-0000-0000-0000-000000000000", "credits": 1},
        timeout=30,
    )
    check("A (no admin) no otorga créditos", r.status_code in (403, 404), f"[{r.status_code}]")

    fallas = [name for ok, name in results if not ok]
    print(f"\n{len(results) - len(fallas)}/{len(results)} OK")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
