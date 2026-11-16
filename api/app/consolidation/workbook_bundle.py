"""Bounded, values-only assembly. Never joins, cleans or evaluates formulas."""

from io import BytesIO
from time import monotonic
from zipfile import ZipFile

from defusedxml.ElementTree import iterparse
from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.utils.cell import coordinate_to_tuple

from ..engine.loader import validate_source_content

MAX_FILES = 10
MAX_BYTES = 15 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_CELLS = 500_000
MAX_SHEETS = 100
MAX_ROWS = 200_000
MAX_COLUMNS = 300
_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def _check_deadline(deadline: float) -> None:
    if monotonic() > deadline:
        raise ValueError('La union supero el tiempo permitido. Divide los archivos en grupos mas pequenos.')


def _preflight(files: list[tuple[str, bytes]], deadline: float) -> None:
    if not 2 <= len(files) <= MAX_FILES:
        raise ValueError(f'Selecciona entre 2 y {MAX_FILES} archivos Excel.')
    if sum(len(data) for _, data in files) > MAX_BYTES:
        raise ValueError('Los archivos juntos no pueden superar 15 MB.')
    cells = sheets = expanded = surface = 0
    for filename, content in files:
        if not filename.lower().endswith('.xlsx'):
            raise ValueError('Solo se admiten archivos .xlsx.')
        validate_source_content(filename, content)
        with ZipFile(BytesIO(content)) as archive:
            expanded += sum(info.file_size for info in archive.infolist())
            if expanded > MAX_EXPANDED_BYTES:
                raise ValueError('El contenido expandido supera el limite de union.')
            if any(info.file_size > 8 * 1024 * 1024 for info in archive.infolist()
                   if not info.filename.startswith('xl/worksheets/')):
                raise ValueError('Los textos, estilos o metadatos de un Excel superan el limite de union.')
            for name in archive.namelist():
                if not name.startswith('xl/worksheets/') or not name.endswith('.xml'):
                    continue
                sheets += 1
                if sheets > MAX_SHEETS:
                    raise ValueError('La union admite hasta 100 hojas.')
                max_row = max_column = 0
                with archive.open(name) as source:
                    for _, element in iterparse(source, events=('end',)):
                        if element.tag == _NS + 'c':
                            cells += 1
                            row, column = coordinate_to_tuple(element.attrib.get('r', 'A1'))
                            max_row, max_column = max(max_row, row), max(max_column, column)
                            if surface + max_row * max_column > MAX_CELLS:
                                raise ValueError('La superficie total de las hojas supera 500.000 celdas, incluyendo espacios vacios.')
                            if cells > MAX_CELLS or row > MAX_ROWS or column > MAX_COLUMNS:
                                raise ValueError('La union admite 500.000 celdas, 200.000 filas y 300 columnas por hoja.')
                            formula = element.find(_NS + 'f')
                            value = element.find(_NS + 'v')
                            if formula is not None and (value is None or (value.text is None and element.get('t') != 'str')):
                                raise ValueError('Hay formulas sin resultado guardado. Abre los originales en Excel o LibreOffice, recalcula y guardalos antes de unirlos.')
                            element.clear()
                        elif element.tag == _NS + 'row':
                            row_index = int(element.attrib.get('r', max_row + 1))
                            if row_index < 1 or row_index > MAX_ROWS:
                                raise ValueError('Una hoja supera el limite de filas de union.')
                            max_row = max(max_row, row_index)
                            if surface + max_row * max(max_column, 1) > MAX_CELLS:
                                raise ValueError('La superficie total de las hojas supera 500.000 celdas, incluyendo espacios vacios.')
                            element.clear()
                        _check_deadline(deadline)
                surface += max_row * max(max_column, 1)
    if sheets == 0:
        raise ValueError('Los Excel no contienen hojas de datos para unir.')


def _sheet_title(title: str, used: set[str]) -> str:
    candidate = title[:31]
    suffix = 2
    while candidate.casefold() in used:
        ending = f' ({suffix})'
        candidate = title[:31 - len(ending)] + ending
        suffix += 1
    used.add(candidate.casefold())
    return candidate


def combine_workbooks(files: list[tuple[str, bytes]]) -> bytes:
    deadline = monotonic() + 60
    _preflight(files, deadline)
    output = Workbook(write_only=True)
    used: set[str] = set()
    copied_cells = 0
    try:
        for _, content in files:
            source = load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False)
            try:
                for sheet in source.worksheets:
                    target = output.create_sheet(_sheet_title(sheet.title, used))
                    # Trust actual cells, not potentially forged worksheet dimensions.
                    sheet.reset_dimensions()
                    for row_index, row in enumerate(sheet.iter_rows(), 1):
                        _check_deadline(deadline)
                        copied_cells += len(row)
                        if row_index > MAX_ROWS or len(row) > MAX_COLUMNS or copied_cells > MAX_CELLS:
                            raise ValueError('El contenido real de las hojas supera los limites de union.')
                        values = []
                        for cell in row:
                            value = WriteOnlyCell(target, value=cell.value)
                            if isinstance(cell.value, str) and cell.data_type != 'e':
                                value.data_type = 's'
                            value.number_format = cell.number_format
                            values.append(value)
                        target.append(values)
            finally:
                source.close()
        result = BytesIO()
        output.save(result)
        return result.getvalue()
    finally:
        # write-only sheets use temporary XML files, also on failed/cancelled runs.
        for sheet in output.worksheets:
            if not sheet.closed:
                sheet.close()
            writer = sheet._writer
            if writer is not None:
                from os.path import exists
                if exists(writer.out):
                    writer.cleanup()
        output.close()
