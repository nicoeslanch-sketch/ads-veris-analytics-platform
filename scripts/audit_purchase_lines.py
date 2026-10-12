"""Independent read-only purchase check for the user-supplied PYME fixture.

No engine imports. Never writes the source workbook or fits values to the control.
The reference is quantity times stated cost, not net purchases or cash paid.
"""

import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path

import openpyxl

from audit_pyme_control import key, number, records


def audit(path):
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        headers = records(workbook['Compras'])
        lines = records(workbook['Detalle_Compras'])
        products = {key(row['IDProducto']) for row in records(workbook['Productos'])}
    finally:
        workbook.close()
    grouped = defaultdict(list)
    for header in headers:
        grouped[key(header['IDCompra'])].append(header)
    safe = {identity: copies[0] for identity, copies in grouped.items() if identity and len({
        tuple((name, key(value)) for name, value in row.items() if name != 'IDCompra')
        for row in copies}) == 1}
    total, included, issues, months = Decimal(0), 0, Counter(), defaultdict(Decimal)
    for row in lines:
        header = safe.get(key(row['IDCompra']))
        if not header:
            issues['unmatched_header'] += 1
            continue
        status = key(header['EstadoCompra'])
        if status.startswith(('anulad', 'cancelad')):
            issues['cancelled_lines'] += 1
            continue
        if status not in {'recibida', 'recibido', 'pendiente'}:
            issues['unknown_status'] += 1
            continue
        qty, cost = number(row['Cantidad']), number(row['CostoUnitarioCompra_CLP'])
        if qty is None or cost is None or qty < 0 or cost < 0:
            issues['invalid_numbers'] += 1
            continue
        if not key(row['IDProducto']) or not key(row['Linea']):
            issues['missing_line_or_product'] += 1
            continue
        if key(row['IDProducto']) not in products:
            issues['unknown_catalog_product_with_declared_cost'] += 1
        value = qty * cost
        date = str(header['FechaCompra'])[:7]
        months[date] += value
        total += value
        included += 1
    return {'source': path.name, 'local_only': True, 'unit': 'CLP',
            'definition': 'Quantity times stated unit cost, including pending non-cancelled purchases; not net of tax and not cash paid',
            'headers': len(headers), 'detail_lines': len(lines), 'included_lines': included,
            'value': float(total), 'issues': dict(issues),
            'by_month': {month: float(value) for month, value in sorted(months.items())}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('workbook', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--engine-result', type=Path)
    args = parser.parse_args()
    result = audit(args.workbook)
    if args.engine_result:
        observed = json.loads(args.engine_result.read_text(encoding='utf-8'))['business']['operacion']['compras_valorizadas']
        result['comparison'] = {'value_equal': observed['valor'] == result['value'],
                                'line_count_equal': observed['lineas_valorizadas'] == result['included_lines'],
                                'engine_state': observed['estado'],
                                'engine_coverage': observed['cobertura_datos_pct']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    if 'comparison' in result and not all(result['comparison'][key] for key in ('value_equal', 'line_count_equal')):
        raise SystemExit(1)
