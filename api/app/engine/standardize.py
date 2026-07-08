"""Estandarización del dataset (SPEC §6, POST /standardize) — motor Fase 7.

Unifica nombres y textos duplicados, estandariza fechas (DD/MM/YYYY) y números
(formato chileno: $ y punto de miles → número plano), y normaliza
mayúsculas/minúsculas/tildes. Opera sobre DataFrames de solo texto.

Mejoras profesionales Fase 7 (§5):
- Detección de tipo con **muestra aleatoria determinista** (no las primeras
  200 filas: un archivo ordenado ya no misclasifica) y **confianza por columna**.
- Números ambiguos ("850.000" ¿miles o decimal?) se deciden por **consistencia
  de toda la columna**, no celda a celda.
- Fechas: **formato dominante por columna** (dayfirst detectado, no fijo) y
  soporte de **meses en texto** ("01 mayo 2026", "1 de mayo de 2026").
- **Fuzzy matching** de typos ("Santigo" → "Santiago") con distancia de
  Levenshtein acotada, además de la unificación por frecuencia.
"""

import random
import re
import warnings

import pandas as pd

from .mapping import norm_key, strip_accents_lower

# Valores que se consideran "sin dato" además del string vacío.
MISSING_TOKENS = {"", "-", "--", "n/a", "na", "null", "none", "s/i", "sin dato"}

DATE_HINTS = ("fecha", "date", "periodo", "emision", "vencimiento")
_DATE_SHAPE = re.compile(r"^\s*\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}\s*$")
_NUMBER_SHAPE = re.compile(r"^\s*-?\s*\$?\s*-?[\d.,]+\s*$")

# Fechas con mes en texto: "01 mayo 2026", "1 de mayo de 2026", "3-ene-26".
_DATE_TEXT_SHAPE = re.compile(
    r"^\s*(\d{1,2})[\s\-/]*(?:de\s+)?([a-z]{3,12})\.?[\s\-/]*(?:de(?:l)?\s+)?(\d{2,4})\s*$"
)
_MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
    "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12,
}

_TYPE_SAMPLE_SIZE = 300
_TYPE_SAMPLE_SEED = 20260706  # determinista: mismos datos → misma clasificación


def is_missing(value: str) -> bool:
    return str(value).strip().lower() in MISSING_TOKENS


def missing_mask(series: pd.Series) -> pd.Series:
    """Máscara vectorizada de valores 'sin dato' (mucho más rápida que .map)."""
    normalized = series.astype(str).str.strip().str.lower()
    return normalized.isin(MISSING_TOKENS)


def normalize_headers(df: pd.DataFrame) -> int:
    """Limpia encabezados in-place. Devuelve cuántos cambiaron."""
    changes = 0
    seen: dict[str, int] = {}
    new_columns: list[str] = []
    for index, col in enumerate(df.columns):
        name = re.sub(r"\s+", " ", str(col)).strip()
        if not name or name.lower().startswith("unnamed"):
            name = f"columna_{index + 1}"
        if name != str(col):
            changes += 1
        key = strip_accents_lower(name)
        count = seen.get(key, 0)
        seen[key] = count + 1
        if count:
            name = f"{name}_{count + 1}"
            changes += 1
        new_columns.append(name)
    df.columns = new_columns
    return changes


def _sample_values(series: pd.Series) -> list[str]:
    """Muestra aleatoria determinista de valores con dato (§5.4)."""
    values = [str(v) for v in series if not is_missing(v)]
    if len(values) <= _TYPE_SAMPLE_SIZE:
        return values
    rng = random.Random(_TYPE_SAMPLE_SEED)
    return rng.sample(values, _TYPE_SAMPLE_SIZE)


def _looks_like_date(value: str) -> bool:
    return bool(
        _DATE_SHAPE.match(value) or _DATE_TEXT_SHAPE.match(strip_accents_lower(value))
    )


def detect_value_type_confidence(series: pd.Series, column_name: str) -> tuple[str, float]:
    """Clasifica una columna como 'fecha', 'numero' o 'texto' + confianza 0–1."""
    values = _sample_values(series)
    if not values:
        return "texto", 0.0
    date_like = sum(_looks_like_date(v) for v in values)
    number_like = sum(bool(_NUMBER_SHAPE.match(v)) for v in values)
    name = strip_accents_lower(column_name)
    date_ratio = date_like / len(values)
    number_ratio = number_like / len(values)
    if date_ratio >= 0.6 or (any(h in name for h in DATE_HINTS) and date_like > 0):
        return "fecha", round(max(date_ratio, 0.6 if date_like else 0.0), 2)
    if number_ratio >= 0.6:
        return "numero", round(number_ratio, 2)
    return "texto", round(1 - max(date_ratio, number_ratio), 2)


def detect_value_type(series: pd.Series, column_name: str) -> str:
    """Compatibilidad: solo el tipo (la confianza vive en el reporte)."""
    return detect_value_type_confidence(series, column_name)[0]


# ── Fechas ────────────────────────────────────────────────────────────────────


def column_dayfirst(series: pd.Series) -> bool:
    """Formato dominante de la columna (§5.6): ¿el primer token es el día?

    Si algún valor tiene primer token > 12 → día primero (es-CL, definitivo).
    Si algún valor tiene segundo token > 12 → mes primero.
    Sin evidencia → día primero (convención chilena)."""
    day_first_evidence = month_first_evidence = 0
    for value in _sample_values(series):
        text = str(value).strip().split(" ")[0]
        if not _DATE_SHAPE.match(text):
            continue
        parts = re.split(r"[-/.]", text)
        if len(parts) != 3:
            continue
        try:
            first, second = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if first > 31:  # ISO yyyy-mm-dd: el orden lo resuelve pandas
            continue
        if 12 < first <= 31:
            day_first_evidence += 1
        elif 12 < second <= 31:
            month_first_evidence += 1
    if day_first_evidence and not month_first_evidence:
        return True
    if month_first_evidence and not day_first_evidence:
        return False
    return day_first_evidence >= month_first_evidence


def _parse_text_month_date(text: str) -> pd.Timestamp | None:
    match = _DATE_TEXT_SHAPE.match(strip_accents_lower(text))
    if not match:
        return None
    day_raw, month_raw, year_raw = match.groups()
    month = _MONTHS_ES.get(month_raw)
    if month is None:
        return None
    year = int(year_raw)
    if year < 100:
        year += 2000 if year < 70 else 1900
    try:
        return pd.Timestamp(year=year, month=month, day=int(day_raw))
    except ValueError:
        return None


def parse_date(value: str, dayfirst: bool = True) -> pd.Timestamp | None:
    text = str(value).strip()
    if is_missing(text):
        return None
    text_month = _parse_text_month_date(text)
    if text_month is not None:
        return text_month
    if not _DATE_SHAPE.match(text):
        # También aceptar fechas ya ISO con hora ("2026-05-01 00:00:00")
        text = text.split(" ")[0]
        if is_missing(text) or not _DATE_SHAPE.match(text):
            return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(text, dayfirst=dayfirst, errors="coerce")
    return None if pd.isna(parsed) else parsed


# ── Números ───────────────────────────────────────────────────────────────────


def column_dot3_convention(series: pd.Series) -> str:
    """Convención de la columna para el caso ambiguo "###.###" (§5.5).

    Devuelve 'miles' (es-CL: 850.000 = ochocientos cincuenta mil) o 'decimal'
    (850.000 = 850 con tres decimales). Se decide por consistencia:
    - Si la columna usa coma decimal o puntos múltiples → el punto es de miles.
    - Si la columna tiene valores con 1–2 decimales tras un único punto y
      ningún indicio de miles → el punto es decimal en toda la columna.
    - Sin evidencia → 'miles' (convención chilena)."""
    decimal_votes = miles_votes = 0
    for value in _sample_values(series):
        text = str(value).strip().replace("$", "").replace(" ", "").lstrip("-")
        if not re.match(r"^[\d.,]+$", text):
            continue
        if "," in text or text.count(".") > 1:
            miles_votes += 1
            continue
        if "." in text:
            right = text.split(".")[1]
            if len(right) in (1, 2):
                decimal_votes += 1
    if decimal_votes and not miles_votes:
        return "decimal"
    return "miles"


def parse_number(value: str, dot3_convention: str = "miles") -> float | None:
    text = str(value).strip().replace("$", "").replace(" ", "")
    if not text or not re.match(r"^-?[\d.,]+$", text):
        return None
    negative = text.startswith("-")
    text = text.lstrip("-")
    if "," in text and "." in text:
        # Formato chileno completo: 1.234.567,89
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        # Coma como separador decimal (es-CL)
        text = text.replace(",", ".")
    elif text.count(".") > 1:
        # Solo puntos de miles: 1.234.567
        text = text.replace(".", "")
    elif "." in text:
        left, right = text.split(".")
        # "850.000": ambiguo → decide la convención de la columna (§5.5)
        if len(right) == 3 and len(left) >= 1 and dot3_convention == "miles":
            text = left + right
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def format_number(number: float) -> str:
    if number == int(number):
        return str(int(number))
    return f"{number:.2f}"


# ── Textos: unificación por frecuencia + fuzzy matching ──────────────────────


def _levenshtein_leq(a: str, b: str, max_distance: int) -> bool:
    """¿distancia de Levenshtein(a, b) ≤ max_distance? DP con corte temprano."""
    if abs(len(a) - len(b)) > max_distance:
        return False
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        row_min = i
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > max_distance:
            return False
        previous = current
    return previous[-1] <= max_distance


_FUZZY_MAX_UNIQUE_KEYS = 400
_FUZZY_MIN_KEY_LEN = 4


def _fuzzy_merge_keys(frequencies: dict[str, dict[str, int]]) -> dict[str, str]:
    """Fusiona claves raras con typos hacia claves frecuentes cercanas (§5.11).

    Guardas para no fusionar valores legítimamente distintos:
    - Solo columnas con ≤ 400 claves únicas y claves de ≥ 4 caracteres con letras.
    - La variante debe ser rara (≤ 1/3 de la canónica) y la canónica frecuente (≥ 3).
    - Distancia ≤ 1 para claves cortas (≤ 6), ≤ 2 para más largas.
    - Misma letra inicial (evita fusionar "gasto"/"pasto")."""
    if not (2 <= len(frequencies) <= _FUZZY_MAX_UNIQUE_KEYS):
        return {}
    totals = {key: sum(variants.values()) for key, variants in frequencies.items()}
    frequent = [k for k, t in totals.items() if t >= 3]
    merges: dict[str, str] = {}
    for key, total in totals.items():
        if key in frequent or len(key) < _FUZZY_MIN_KEY_LEN or not any(c.isalpha() for c in key):
            continue
        max_distance = 1 if len(key) <= 6 else 2
        for canon in frequent:
            if canon[0] != key[0] or len(canon) < _FUZZY_MIN_KEY_LEN:
                continue
            if total > max(2, totals[canon] // 3):
                continue
            if _levenshtein_leq(key, canon, max_distance):
                merges[key] = canon
                break
    return merges


def _normalize_text_column(series: pd.Series) -> tuple[pd.Series, int, list[list[str]]]:
    """Recorta espacios, limpia placeholders y unifica variantes de un mismo texto.

    Devuelve (serie, cambios, ejemplos_de_fusiones_fuzzy). Las variantes que
    solo difieren en mayúsculas/tildes/espacios se reemplazan por la forma más
    frecuente; los typos cercanos se fusionan con Levenshtein acotado."""
    stripped = series.map(lambda v: "" if is_missing(v) else re.sub(r"\s+", " ", str(v)).strip())
    changes = int((stripped != series.map(str)).sum())

    frequencies: dict[str, dict[str, int]] = {}
    for value in stripped:
        if not value:
            continue
        # norm_key agrupa variantes que solo difieren en mayúsculas, tildes
        # o puntuación de formato (ej: "76.123.456-7" y "76123456-7").
        key = norm_key(value)
        bucket = frequencies.setdefault(key, {})
        bucket[value] = bucket.get(value, 0) + 1

    def _pick_canonical(variants: dict[str, int]) -> str:
        # Más frecuente; ante empate, prefiere la forma con mayúscula inicial.
        return max(variants.items(), key=lambda kv: (kv[1], kv[0][:1].isupper(), kv[0]))[0]

    canonical = {key: _pick_canonical(variants) for key, variants in frequencies.items()}

    # Fuzzy: claves raras que son typos de una clave frecuente (§5.11).
    fuzzy_examples: list[list[str]] = []
    for rare_key, canon_key in _fuzzy_merge_keys(frequencies).items():
        if len(fuzzy_examples) < 5:
            fuzzy_examples.append([canonical[rare_key], canonical[canon_key]])
        canonical[rare_key] = canonical[canon_key]

    unified = stripped.map(lambda v: canonical[norm_key(v)] if v else v)
    changes += int((unified != stripped).sum())
    return unified, changes, fuzzy_examples


# ── Pipeline de estandarización ──────────────────────────────────────────────


def standardize_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Devuelve (df_estandarizado, reporte de cambios, tipos y confianza)."""
    result = df.copy()
    renamed_headers = normalize_headers(result)

    column_types: dict[str, str] = {}
    column_confidence: dict[str, float] = {}
    numeric_conventions: dict[str, str] = {}
    date_dayfirst: dict[str, bool] = {}
    fuzzy_total = 0
    fuzzy_examples: list[list[str]] = []
    text_changes = date_changes = number_changes = 0

    for col in result.columns:
        ctype, confidence = detect_value_type_confidence(result[col], col)
        column_types[col] = ctype
        column_confidence[col] = confidence

        if ctype == "texto":
            result[col], changed, examples = _normalize_text_column(result[col])
            text_changes += changed
            if examples:
                fuzzy_total += len(examples)
                fuzzy_examples.extend(examples[: max(0, 5 - len(fuzzy_examples))])
        elif ctype == "fecha":
            dayfirst = column_dayfirst(result[col])
            date_dayfirst[col] = dayfirst

            def _standardize_date(value: str) -> str:
                if is_missing(value):
                    return ""
                parsed = parse_date(value, dayfirst=dayfirst)
                return str(value).strip() if parsed is None else parsed.strftime("%d/%m/%Y")

            new = result[col].map(_standardize_date)
            date_changes += int((new != result[col].map(str)).sum())
            result[col] = new
        else:
            convention = column_dot3_convention(result[col])
            numeric_conventions[col] = convention

            def _standardize_number(value: str) -> str:
                if is_missing(value):
                    return ""
                number = parse_number(value, dot3_convention=convention)
                return str(value).strip() if number is None else format_number(number)

            new = result[col].map(_standardize_number)
            number_changes += int((new != result[col].map(str)).sum())
            result[col] = new

    report = {
        "column_types": column_types,
        "column_confidence": column_confidence,
        "convenciones_numericas": numeric_conventions,
        "fechas_dayfirst": date_dayfirst,
        "fusiones_texto": {"total": fuzzy_total, "ejemplos": fuzzy_examples},
        "cambios": {
            "encabezados_normalizados": renamed_headers,
            "textos_normalizados": text_changes,
            "fechas_estandarizadas": date_changes,
            "numeros_estandarizados": number_changes,
        },
    }
    return result, report
