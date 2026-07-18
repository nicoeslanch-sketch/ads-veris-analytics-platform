"""Safe dataframe exports for downloadable files."""

import re

import pandas as pd

from .standardize import map_unique, parse_number

# Bug #5: un negativo contable estandarizado ("(12.990)" → "-12990") es un
# número legítimo, no un intento de inyección de fórmulas — no debe llevar
# apóstrofe de escape (eso lo convierte en texto y deja de sumar en Excel).
_NEGATIVE_NUMBER_RE = re.compile(r"^-[\d.,]+$")


def neutralize_excel_formula(value):
    """Return a value safe to open in spreadsheet software.

    Excel/Sheets can interpret cells starting with =, +, - or @ as formulas.
    We only neutralize the exported copy; internal cleaned data is unchanged.
    """
    if value is None:
        return value
    try:
        if pd.isna(value):
            return value
    except TypeError:
        pass
    text = str(value)
    stripped = text.lstrip()
    if stripped.startswith("-") and _NEGATIVE_NUMBER_RE.match(stripped):
        # Además de no escaparlo, hay que devolverlo como número real: pandas
        # escribe un `str` de Python como celda de texto en el .xlsx sin
        # importar el apóstrofe (el tipo de celda es explícito, no se
        # autodetecta como en un CSV) — así seguiría sin sumar en pivotes.
        try:
            return float(stripped)
        except ValueError:
            pass
    if stripped.startswith(("=", "+", "-", "@")):
        return "'" + text
    return value


def safe_export_dataframe(
    df: pd.DataFrame,
    numeric_columns: set[str] | list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Neutraliza fórmulas y conserva números como celdas numéricas.

    El pipeline trabaja deliberadamente con texto para no perder evidencia.
    En la copia exportada solo se tipan los valores que el motor pudo
    interpretar; un valor ambiguo o inválido permanece literal y auditable.
    """
    exported = df.copy()
    requested = set(numeric_columns or ())
    requested.update(
        str(column)
        for column in exported.columns
        if pd.api.types.is_numeric_dtype(exported[column])
    )
    for column in requested:
        if column not in exported.columns:
            continue
        original = exported[column]
        parsed = map_unique(original, parse_number)
        valid = parsed.notna()
        ambiguous_comma = original.astype(str).str.strip().str.match(
            r"^[+-]?\d{1,3},\d{3}$"
        )
        valid &= ~ambiguous_comma
        if not bool(valid.any()):
            continue
        typed = original.astype(object).copy()
        typed.loc[valid] = pd.to_numeric(parsed.loc[valid], errors="coerce")
        exported[column] = typed
    return exported.apply(lambda column: column.map(neutralize_excel_formula))
