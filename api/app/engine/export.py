"""Safe dataframe exports for downloadable files."""

import pandas as pd


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
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return value


def safe_export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    return df.apply(lambda column: column.map(neutralize_excel_formula))
