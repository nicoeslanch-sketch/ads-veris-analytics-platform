"""Carga de archivos Excel/CSV hacia DataFrames de solo texto.

Todo se lee como string: el motor de estandarización decide después qué es
fecha, número o texto. Celda vacía = string vacío (nunca NaN), para que las
comparaciones y conteos sean deterministas.
"""

import io

import pandas as pd

SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls")
MAX_ROWS = 200_000


class UnsupportedFileError(ValueError):
    pass


def _detect_separator(sample: str) -> str:
    first_line = sample.splitlines()[0] if sample.splitlines() else ""
    candidates = {";": first_line.count(";"), ",": first_line.count(","), "\t": first_line.count("\t")}
    best = max(candidates, key=lambda k: candidates[k])
    return best if candidates[best] > 0 else ","


def load_dataframe(filename: str, content: bytes) -> pd.DataFrame:
    name = (filename or "").lower()
    if not name.endswith(SUPPORTED_EXTENSIONS):
        raise UnsupportedFileError(
            "Formato no soportado. Sube un archivo Excel (.xlsx) o CSV (.csv)."
        )

    if name.endswith(".csv"):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")
        if not text.strip():
            raise UnsupportedFileError("El archivo CSV está vacío.")
        df = pd.read_csv(
            io.StringIO(text),
            sep=_detect_separator(text),
            dtype=str,
            keep_default_na=False,
            skip_blank_lines=True,
        )
    else:
        df = pd.read_excel(io.BytesIO(content), dtype=str)
        df = df.fillna("")
        df = df.astype(str)
        # pandas serializa NaN de celdas ya convertidas como el texto "nan"
        df = df.replace({"nan": "", "NaT": "", "None": ""})

    if df.empty or len(df.columns) == 0:
        raise UnsupportedFileError("El archivo no tiene datos que procesar.")
    if len(df) > MAX_ROWS:
        raise UnsupportedFileError(
            f"El archivo supera el máximo de {MAX_ROWS:,} filas para esta versión.".replace(",", ".")
        )
    return df.reset_index(drop=True)
