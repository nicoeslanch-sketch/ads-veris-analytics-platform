"""Safe dataframe exports for downloadable files."""

from numbers import Number

import pandas as pd

from .standardize import map_unique, parse_date, parse_number


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
    # Los valores de columnas numericas ya fueron convertidos antes de llegar
    # aqui. Nunca reinterpretar un texto como numero: un SKU "-12.990" o un
    # valor original de auditoria debe conservar exactamente sus caracteres.
    if isinstance(value, Number):
        return value
    text = str(value)
    stripped = text.lstrip()
    if stripped.startswith(("=", "+", "-", "@")):
        return "'" + text
    return value


def safe_export_dataframe(
    df: pd.DataFrame,
    numeric_columns: set[str] | list[str] | tuple[str, ...] | None = None,
    date_columns: set[str] | list[str] | tuple[str, ...] | None = None,
    *,
    canonical_numeric: bool = False,
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
        parsed = map_unique(
            original,
            lambda value: parse_number(
                value,
                # Las salidas del limpiador ya usan punto decimal canonico.
                # Reinterpretar "1.234" como miles cambiaba 1,234→1.234→1234
                # justo al escribir el XLSX.
                dot3_convention="decimal" if canonical_numeric else "miles",
                comma3_convention="decimal",
            ),
        )
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
    for column in set(date_columns or ()):
        if column not in exported.columns:
            continue
        original = exported[column]
        parsed = map_unique(original, parse_date)
        valid = parsed.notna()
        if not bool(valid.any()):
            continue
        typed = original.astype(object).copy()
        typed.loc[valid] = parsed.loc[valid]
        exported[column] = typed
    # Neutralización dirigida: detectar los prefijos peligrosos con operaciones
    # vectorizadas y llamar a la función celda a celda SOLO en los sospechosos.
    # Aplicarla sobre las ~400.000 celdas del libro multihoja era uno de los
    # costos dominantes de la exportación.
    for column in exported.columns:
        series = exported[column]
        if pd.api.types.is_numeric_dtype(series):
            continue
        text = series.astype(str).str.lstrip()
        suspects = series.notna() & text.str.startswith(("=", "+", "-", "@"))
        if bool(suspects.any()):
            exported.loc[suspects, column] = series.loc[suspects].map(
                neutralize_excel_formula
            )
    return exported
