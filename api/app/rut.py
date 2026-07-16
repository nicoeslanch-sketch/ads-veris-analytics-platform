"""RUT chileno: normalización, validación (módulo 11) y enmascarado (Fase 14).

La normalización debe ser IDÉNTICA en frontend, backend y RPC SQL (migración
0016): quitar puntos/espacios/guiones, K mayúscula, formato canónico CUERPO-DV.
La validación estructural + dígito verificador es la autoridad — no hay piso
mínimo arbitrario de cuerpo (existen RUN legítimos antiguos bajo 1.000.000) y
los patrones "llamativos" con DV válido se aceptan: un patrón repetitivo no
demuestra que el RUT sea falso. El antiabuso se resuelve con unicidad en la
base, correo confirmado, rate limiting y auditoría — no bloqueando números.

Privacidad: el RUT completo jamás va en URLs, logs ni JWT. Para mostrar se usa
`mask_rut` (12.***.***-5). Idempotencia garantizada:
normalize_rut(normalize_rut(x)) == normalize_rut(x).
"""

import re

_CLEAN_RE = re.compile(r"[.\s\-]")
_CANONICAL_RE = re.compile(r"^(\d{1,9})-([\dK])$")


def normalize_rut(raw: str | None) -> str | None:
    """'12.345.678-k' | '12345678K' | '12 345 678 K' → '12345678-K'.

    Devuelve None si la entrada no tiene la estructura cuerpo+DV (eso incluye
    contenido adicional, letras en el cuerpo o largo fuera de rango).
    """
    if not raw:
        return None
    compact = _CLEAN_RE.sub("", raw.strip()).upper()
    if not 2 <= len(compact) <= 10:
        return None
    body, dv = compact[:-1], compact[-1]
    if not body.isdigit() or dv not in "0123456789K":
        return None
    # Sin ceros a la izquierda en el canónico: '012345678-5' ≡ '12345678-5'.
    body = body.lstrip("0") or "0"
    if body == "0":
        return None
    return f"{body}-{dv}"


def compute_dv(body: str) -> str:
    """Dígito verificador por módulo 11 (algoritmo oficial chileno)."""
    total = 0
    factor = 2
    for digit in reversed(body):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - (total % 11)
    if remainder == 11:
        return "0"
    if remainder == 10:
        return "K"
    return str(remainder)


def is_valid_rut(raw: str | None) -> bool:
    """Estructura canónica + módulo 11. NO verifica titularidad ni
    representación legal: solo que el número está bien formado."""
    normalized = normalize_rut(raw)
    if not normalized:
        return False
    match = _CANONICAL_RE.match(normalized)
    if not match:
        return False
    body, dv = match.groups()
    return compute_dv(body) == dv


def mask_rut(normalized: str) -> str:
    """'12345678-5' → '12.***.***-5' (solo el primer grupo y el DV visibles)."""
    match = _CANONICAL_RE.match(normalized)
    if not match:
        return "***"
    body, dv = match.groups()
    prefix = body[:-6] if len(body) > 6 else body[:1]
    return f"{prefix}.***.***-{dv}"
