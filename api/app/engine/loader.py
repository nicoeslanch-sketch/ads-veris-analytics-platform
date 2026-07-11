"""Carga de archivos Excel/CSV hacia DataFrames de solo texto (Fase 7, §5.12).

Todo se lee como string: el motor de estandarización decide después qué es
fecha, número o texto. Celda vacía = string vacío (nunca NaN), para que las
comparaciones y conteos sean deterministas.

Mejoras profesionales Fase 7:
- Excel con varias hojas: se elige la hoja con más datos (antes se leía la
  primera en silencio) y se informa cuáles quedaron fuera.
- Filas de título sobre el encabezado ("REPORTE VENTAS 2026"): se detecta la
  fila real de encabezados y se omiten las de arriba, con aviso.
- CSV: el separador se decide mirando varias líneas (no solo la primera).

Fase 8:
- Filas de totales al FINAL ("Total", "Subtotal", "Total general", "Suma"):
  no son datos — duplicarían los ingresos en las métricas. Se omiten con aviso.

`load_dataframe_with_report` devuelve (df, reporte_de_carga);
`load_dataframe` se mantiene como wrapper compatible.
"""

import io
import re
import unicodedata
import zipfile

import pandas as pd

SUPPORTED_EXTENSIONS = (".csv", ".xlsx")
MAX_ROWS = 200_000
_HEADER_SCAN_ROWS = 10

# Fase 10 §8.2: un .xlsx es un ZIP — 15 MB comprimidos pueden expandirse a
# cientos de MB (zip bomb) y tumbar el proceso al leerlo con pandas.
_MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 120


def _guard_xlsx_zip(content: bytes) -> None:
    """Rechaza .xlsx corruptos o con expansión anómala ANTES de cargarlos."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            total_uncompressed = sum(info.file_size for info in zf.infolist())
    except zipfile.BadZipFile:
        raise UnsupportedFileError(
            "El archivo .xlsx está dañado o no es un Excel válido. "
            "Ábrelo en Excel y guárdalo nuevamente como .xlsx."
        )
    if total_uncompressed > _MAX_UNCOMPRESSED_BYTES:
        raise UnsupportedFileError(
            "El Excel se expande a un tamaño demasiado grande para procesarlo. "
            "Divide la base en archivos más pequeños o expórtala como CSV."
        )
    compressed = max(len(content), 1)
    if total_uncompressed / compressed > _MAX_COMPRESSION_RATIO:
        raise UnsupportedFileError(
            "El archivo tiene una compresión anómala y no se puede procesar de "
            "forma segura. Exporta la base como CSV e inténtalo de nuevo."
        )

# Fila-resumen al final de la planilla: su primera celda con texto es una
# etiqueta de total. Solo se revisan las ÚLTIMAS filas (nunca datos del medio).
_TOTAL_ROW_RE = re.compile(
    r"^(sub)?total(es)?( general(es)?)?\b|^suma(s|torias?)?\b|^gran total\b"
)
_MAX_TRAILING_TOTAL_ROWS = 3


def _strip_accents_lower(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()


def _drop_trailing_total_rows(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    """Omite hasta 3 filas de totales al final del archivo (Fase 8)."""
    dropped = 0
    while len(df) > 1 and dropped < _MAX_TRAILING_TOTAL_ROWS:
        first_text = next(
            (str(v).strip() for v in df.iloc[-1] if str(v).strip()), ""
        )
        if not _TOTAL_ROW_RE.match(_strip_accents_lower(first_text)):
            break
        df = df.iloc[:-1]
        dropped += 1
    if dropped:
        report["filas_totales_omitidas"] = dropped
        report["avisos"].append(
            f"Se omitieron {dropped} fila(s) de totales al final del archivo: "
            "son un resumen, no datos, y duplicarían tus indicadores."
        )
    return df


class UnsupportedFileError(ValueError):
    pass


def _detect_separator(sample: str) -> str:
    """Separador más consistente en las primeras líneas con contenido."""
    lines = [line for line in sample.splitlines() if line.strip()][:8]
    if not lines:
        return ","
    scores: dict[str, int] = {}
    for sep in (";", ",", "\t"):
        counts = [line.count(sep) for line in lines]
        if counts[0] > 0 and len(set(counts)) == 1:
            # Mismo número de separadores en todas las líneas → muy confiable.
            scores[sep] = counts[0] * 100
        else:
            scores[sep] = counts[0]
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else ","


def _clean_string_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.fillna("")
    df = df.astype(str)
    # pandas serializa NaN de celdas ya convertidas como el texto "nan"
    return df.replace({"nan": "", "NaT": "", "None": ""})


def _detect_header_row(raw: pd.DataFrame) -> int:
    """Fila real de encabezados dentro de las primeras _HEADER_SCAN_ROWS.

    Un encabezado tiene varias celdas con contenido; una fila de título suele
    tener 1–2. Se elige la primera fila con ≥60% de celdas no vacías y al
    menos 2 con contenido. Si ninguna califica, se usa la fila 0 (compatible
    con el comportamiento anterior)."""
    total_cols = len(raw.columns)
    if total_cols <= 1:
        return 0
    limit = min(_HEADER_SCAN_ROWS, len(raw))
    for idx in range(limit):
        values = [str(v).strip() for v in raw.iloc[idx].tolist()]
        non_empty = sum(1 for v in values if v)
        if non_empty >= 2 and non_empty / total_cols >= 0.6:
            return idx
    return 0


def _load_excel(content: bytes, report: dict, sheet: str | None = None) -> pd.DataFrame:
    _guard_xlsx_zip(content)
    book = pd.ExcelFile(io.BytesIO(content))
    sheet_names = list(book.sheet_names)
    report["hojas_disponibles"] = sheet_names

    # Fase 10 §8.3: el usuario puede elegir la hoja; sin elección, se usa la
    # hoja con más celdas con datos (muestra de 60 filas por hoja).
    if sheet is not None and sheet in sheet_names:
        best_sheet = sheet
        report["hoja_usada"] = best_sheet
        if len(sheet_names) > 1:
            report["avisos"].append(
                f"Se usó la hoja '{best_sheet}' (elegida por ti)."
            )
    else:
        best_sheet = sheet_names[0]
        best_score = -1
        for name in sheet_names:
            sample = _clean_string_frame(book.parse(name, header=None, nrows=60, dtype=str))
            score = int((sample != "").sum().sum())
            if score > best_score:
                best_sheet, best_score = name, score
        report["hoja_usada"] = best_sheet
        if len(sheet_names) > 1:
            others = [s for s in sheet_names if s != best_sheet]
            report["avisos"].append(
                f"El archivo tiene {len(sheet_names)} hojas; se usó '{best_sheet}' "
                f"(la con más datos). Hojas no procesadas: {', '.join(others)}. "
                "Puedes elegir otra hoja desde Estandarización."
            )

    raw = _clean_string_frame(book.parse(best_sheet, header=None, dtype=str))
    header_row = _detect_header_row(raw)
    if header_row > 0:
        report["filas_titulo_omitidas"] = header_row
        report["avisos"].append(
            f"Se omitieron {header_row} fila(s) de título sobre los encabezados."
        )
    headers = [str(v).strip() for v in raw.iloc[header_row].tolist()]
    df = raw.iloc[header_row + 1 :].reset_index(drop=True)
    df.columns = headers
    return df


def load_dataframe_with_report(
    filename: str, content: bytes, sheet: str | None = None
) -> tuple[pd.DataFrame, dict]:
    """Carga el archivo y devuelve (df, reporte_de_carga con avisos)."""
    report: dict = {
        "avisos": [],
        "hoja_usada": None,
        "hojas_disponibles": [],
        "filas_titulo_omitidas": 0,
        "filas_totales_omitidas": 0,
    }
    name = (filename or "").lower()
    if name.endswith(".xls"):
        # Fase 10 §8.1: el Excel antiguo (.xls) requiere otra librería y fallaba
        # en ejecución aunque la UI lo aceptara. Mensaje claro en vez de promesa rota.
        raise UnsupportedFileError(
            "El formato Excel antiguo (.xls) no está soportado. Abre el archivo en "
            "Excel y guárdalo como .xlsx (o expórtalo como CSV) para procesarlo."
        )
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
        separator = _detect_separator(text)
        report["separador"] = separator
        df = pd.read_csv(
            io.StringIO(text),
            sep=separator,
            dtype=str,
            keep_default_na=False,
            skip_blank_lines=True,
        )
    else:
        df = _load_excel(content, report, sheet=sheet)

    # Filas completamente vacías al final (frecuentes en Excel) no son datos.
    # Fase 11: vectorizado por columna (antes era fila por fila con apply).
    non_empty_mask = pd.Series(False, index=df.index)
    for col in df.columns:
        non_empty_mask |= df[col].astype(str).str.strip() != ""
    df = df[non_empty_mask].reset_index(drop=True)

    # Filas de totales al final ("Total", "Suma"): resumen, no datos (Fase 8).
    df = _drop_trailing_total_rows(df, report).reset_index(drop=True)

    if df.empty or len(df.columns) == 0:
        raise UnsupportedFileError("El archivo no tiene datos que procesar.")
    if len(df) > MAX_ROWS:
        raise UnsupportedFileError(
            f"El archivo supera el máximo de {MAX_ROWS:,} filas para esta versión.".replace(",", ".")
        )
    return df.reset_index(drop=True), report


def load_dataframe(filename: str, content: bytes) -> pd.DataFrame:
    """Wrapper compatible: solo el DataFrame (el reporte se descarta)."""
    df, _ = load_dataframe_with_report(filename, content)
    return df
