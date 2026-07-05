"""Estandarización del dataset (SPEC §6, POST /standardize).

Unifica nombres y textos duplicados, estandariza fechas (DD/MM/YYYY) y números
(formato chileno: $ y punto de miles → número plano), y normaliza
mayúsculas/minúsculas/tildes. Opera sobre DataFrames de solo texto.
"""

import re
import warnings

import pandas as pd

from .mapping import norm_key, strip_accents_lower

# Valores que se consideran "sin dato" además del string vacío.
MISSING_TOKENS = {"", "-", "--", "n/a", "na", "null", "none", "s/i", "sin dato"}

DATE_HINTS = ("fecha", "date", "periodo", "emision", "vencimiento")
_DATE_SHAPE = re.compile(r"^\s*\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}\s*$")
_NUMBER_SHAPE = re.compile(r"^\s*-?\s*\$?\s*-?[\d.,]+\s*$")


def is_missing(value: str) -> bool:
    return str(value).strip().lower() in MISSING_TOKENS


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


def detect_value_type(series: pd.Series, column_name: str) -> str:
    """Clasifica una columna como 'fecha', 'numero' o 'texto'."""
    values = [str(v) for v in series if not is_missing(v)][:200]
    if not values:
        return "texto"
    date_like = sum(bool(_DATE_SHAPE.match(v)) for v in values)
    number_like = sum(bool(_NUMBER_SHAPE.match(v)) for v in values)
    name = strip_accents_lower(column_name)
    if date_like / len(values) >= 0.6 or (any(h in name for h in DATE_HINTS) and date_like > 0):
        return "fecha"
    if number_like / len(values) >= 0.6:
        return "numero"
    return "texto"


def parse_date(value: str) -> pd.Timestamp | None:
    text = str(value).strip()
    if is_missing(text) or not _DATE_SHAPE.match(text):
        # También aceptar fechas ya ISO con hora ("2026-05-01 00:00:00")
        text = text.split(" ")[0]
        if is_missing(text) or not _DATE_SHAPE.match(text):
            return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    return None if pd.isna(parsed) else parsed


def parse_number(value: str) -> float | None:
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
        # "850.000" es miles en es-CL; "8.5" es decimal
        if len(right) == 3 and len(left) >= 1:
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


def _normalize_text_column(series: pd.Series) -> tuple[pd.Series, int]:
    """Recorta espacios, limpia placeholders y unifica variantes de un mismo texto.

    Las variantes que solo difieren en mayúsculas/tildes/espacios se reemplazan
    por la forma más frecuente (ej: "santiago limitada" → "Santiago Limitada").
    """
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
    unified = stripped.map(lambda v: canonical[norm_key(v)] if v else v)
    changes += int((unified != stripped).sum())
    return unified, changes


def standardize_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Devuelve (df_estandarizado, reporte de cambios y tipos)."""
    result = df.copy()
    renamed_headers = normalize_headers(result)

    column_types: dict[str, str] = {}
    text_changes = date_changes = number_changes = 0

    for col in result.columns:
        ctype = detect_value_type(result[col], col)
        column_types[col] = ctype

        if ctype == "texto":
            result[col], changed = _normalize_text_column(result[col])
            text_changes += changed
        elif ctype == "fecha":
            def _standardize_date(value: str) -> str:
                if is_missing(value):
                    return ""
                parsed = parse_date(value)
                return str(value).strip() if parsed is None else parsed.strftime("%d/%m/%Y")

            new = result[col].map(_standardize_date)
            date_changes += int((new != result[col].map(str)).sum())
            result[col] = new
        else:
            def _standardize_number(value: str) -> str:
                if is_missing(value):
                    return ""
                number = parse_number(value)
                return str(value).strip() if number is None else format_number(number)

            new = result[col].map(_standardize_number)
            number_changes += int((new != result[col].map(str)).sum())
            result[col] = new

    report = {
        "column_types": column_types,
        "cambios": {
            "encabezados_normalizados": renamed_headers,
            "textos_normalizados": text_changes,
            "fechas_estandarizadas": date_changes,
            "numeros_estandarizados": number_changes,
        },
    }
    return result, report
