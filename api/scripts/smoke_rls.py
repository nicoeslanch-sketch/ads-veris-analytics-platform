"""Smoke real de aislamiento RLS/Storage entre dos cuentas de prueba.

En staging o CI no se permite omitir fixtures críticos. Variables:
API_BASE, JWT_A, JWT_B, SUPABASE_URL, SUPABASE_ANON_KEY,
STORAGE_PATH_B y BILLING_ID_B. ``SMOKE_ENV=staging`` activa modo estricto.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx

BASE = os.environ.get("API_BASE", "").rstrip("/")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
JWT_A = os.environ.get("JWT_A", "")
JWT_B = os.environ.get("JWT_B", "")
STORAGE_PATH_B = os.environ.get("STORAGE_PATH_B", "")
BILLING_ID_B = os.environ.get("BILLING_ID_B", "")
SMOKE_ENV = os.environ.get("SMOKE_ENV", os.environ.get("APP_ENV", "local")).lower()
STRICT = SMOKE_ENV in {"staging", "ci", "production"} or os.environ.get("CI", "").lower() in {
    "1",
    "true",
    "yes",
}

results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    results.append((ok, name))
    print(("✓" if ok else "✗"), name, extra)


def _api_headers(jwt: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt}"}


def _supabase_headers(jwt: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {jwt}",
        "apikey": SUPABASE_ANON_KEY,
    }


def _rest_get(table: str, jwt: str, params: dict[str, str]) -> httpx.Response:
    return httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers=_supabase_headers(jwt),
        timeout=30,
    )


def _owned_row(table: str, jwt: str, params: dict[str, str] | None = None) -> dict | None:
    response = _rest_get(
        table,
        jwt,
        {"select": "*", "limit": "1", **(params or {})},
    )
    if response.status_code != 200:
        check(f"B puede consultar {table}", False, f"[{response.status_code}]")
        return None
    rows = response.json()
    if not isinstance(rows, list) or not rows:
        check(
            f"fixture B existe en {table}",
            not STRICT,
            "[sin filas; obligatorio en staging/CI]",
        )
        return None
    return rows[0] if isinstance(rows[0], dict) else None


def _assert_hidden_by_id(table: str, row_id: str, label: str) -> None:
    response = _rest_get(
        table,
        JWT_A,
        {"select": "id", "id": f"eq.{row_id}"},
    )
    hidden = response.status_code == 200 and response.json() == []
    check(f"A no lee {label} de B", hidden, f"[{response.status_code}]")


def _assert_child_rows_hidden(table: str, dataset_id: str, label: str) -> None:
    row_b = _owned_row(table, JWT_B, {"dataset_id": f"eq.{dataset_id}"})
    if row_b is None:
        return
    response = _rest_get(
        table,
        JWT_A,
        {"select": "id", "dataset_id": f"eq.{dataset_id}"},
    )
    hidden = response.status_code == 200 and response.json() == []
    check(f"A no lee {label} de B", hidden, f"[{response.status_code}]")


def _validate_configuration() -> list[str]:
    required = {
        "API_BASE": BASE,
        "JWT_A": JWT_A,
        "JWT_B": JWT_B,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_ANON_KEY": SUPABASE_ANON_KEY,
    }
    if STRICT:
        required.update(
            {
                "STORAGE_PATH_B": STORAGE_PATH_B,
                "BILLING_ID_B": BILLING_ID_B,
            }
        )
    return [name for name, value in required.items() if not value]


def main() -> int:
    missing = _validate_configuration()
    if missing:
        print("Faltan variables obligatorias: " + ", ".join(missing))
        return 2

    # Ambas sesiones deben ser válidas; de lo contrario los 401 no prueban RLS.
    for label, jwt in (("A", JWT_A), ("B", JWT_B)):
        response = httpx.get(f"{BASE}/me", headers=_api_headers(jwt), timeout=20)
        check(f"sesión {label} válida", response.status_code == 200, f"[{response.status_code}]")
    if any(not ok for ok, _ in results):
        return 1

    dataset_b = _owned_row("datasets", JWT_B)
    if dataset_b and dataset_b.get("id"):
        dataset_id = str(dataset_b["id"])
        _assert_hidden_by_id("datasets", dataset_id, "dataset")
        _assert_child_rows_hidden("dataset_columns", dataset_id, "columnas")
        _assert_child_rows_hidden("cleaning_jobs", dataset_id, "limpiezas")

    for table, label in (("analyses", "análisis"), ("activity_log", "actividad")):
        row = _owned_row(table, JWT_B)
        if row and row.get("id"):
            _assert_hidden_by_id(table, str(row["id"]), label)

    billing_b = _owned_row(
        "billing_identities",
        JWT_B,
        {"id": f"eq.{BILLING_ID_B}"} if BILLING_ID_B else None,
    )
    if billing_b and billing_b.get("id"):
        _assert_hidden_by_id("billing_identities", str(billing_b["id"]), "facturación")

    request_b = _owned_row("addon_requests", JWT_B)
    if request_b and request_b.get("id"):
        _assert_hidden_by_id("addon_requests", str(request_b["id"]), "solicitudes")

    if STORAGE_PATH_B:
        storage_response = httpx.get(
            f"{SUPABASE_URL}/storage/v1/object/datasets/{STORAGE_PATH_B}",
            headers=_supabase_headers(JWT_A),
            timeout=30,
        )
        check(
            "A no descarga directamente el archivo de B",
            storage_response.status_code in (400, 401, 403, 404),
            f"[{storage_response.status_code}]",
        )
        api_response = httpx.post(
            f"{BASE}/standardize",
            headers=_api_headers(JWT_A),
            data={"storage_path": STORAGE_PATH_B},
            timeout=60,
        )
        check(
            "A no procesa el archivo de B por API",
            api_response.status_code in (403, 404),
            f"[{api_response.status_code}]",
        )
    elif not STRICT:
        print("· STORAGE_PATH_B no definido: prueba Storage omitida solo en modo local")

    if BILLING_ID_B:
        response = httpx.post(
            f"{BASE}/addons/request",
            headers=_api_headers(JWT_A),
            json={
                "tipo": "upgrade_analista",
                "mensaje": "smoke rls",
                "billing_identity_id": BILLING_ID_B,
            },
            timeout=30,
        )
        check("A no usa billing identity de B", response.status_code == 422, f"[{response.status_code}]")
    elif not STRICT:
        print("· BILLING_ID_B no definido: prueba de facturación omitida solo en modo local")

    response = httpx.get(f"{BASE}/admin/accounts", headers=_api_headers(JWT_A), timeout=30)
    check("A (no admin) no lista cuentas", response.status_code in (403, 404), f"[{response.status_code}]")

    failures = [name for ok, name in results if not ok]
    print(f"\n{len(results) - len(failures)}/{len(results)} OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
