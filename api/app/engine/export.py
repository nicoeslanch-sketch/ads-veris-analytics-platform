"""Safe dataframe exports for downloadable files."""

import re

import pandas as pd

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


def safe_export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    return df.apply(lambda column: column.map(neutralize_excel_formula))
