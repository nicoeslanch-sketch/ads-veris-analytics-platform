"""Local-only source reconciliation; never uploads workbook or oracle contents."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from app.engine.loader import load_dataframes_with_reports, xlsx_sheet_names
from app.engine.relational_ledger import analyze_relational_ledger
from app.routes.pipeline import _analyze_cached
from app.routes.pipeline import _relationships_sync, _relationship_catalog_sync, _relationship_dashboard_sync, _parse_sheet_manifest
from app.routes.assistant import BotRequest

ORACLE_KEYS = ('ventas_emitidas_netas', 'notas_credito_netas', 'ventas_netas', 'iva_debito_neto',
    'costo_ventas_neto', 'utilidad_bruta', 'gastos_operacionales_netos', 'nominas', 'comisiones_cobro',
    'resultado_antes_impuestos', 'cuentas_por_cobrar', 'cuentas_por_pagar', 'stock_unidades',
    'inventario_valorizado', 'ventas_emitidas', 'ventas_anuladas', 'notas_credito', 'lineas_fisicas',
    'depositos_netos', 'flujo_caja_antes_iva', 'compras_netas', 'iva_credito', 'clientes_compradores',
    'lineas_emitidas', 'unidades_emitidas')


def compare_oracle(frames, report, oracle):
    checks = []
    def check(label, actual, expected):
        checks.append({'check': label, 'actual': actual, 'expected': expected,
            'passed': actual is not None and abs(actual - expected) <= 0.01})
    for i, key in enumerate(ORACLE_KEYS, 1):
        check(key, report['kpis'].get(key), oracle['metrics'][f'K{i:02d}']['valor'])
    monthly_keys = {'ventas_netas': 'ventas_netas', 'costo_ventas_neto': 'costo_ventas_neto',
        'utilidad_bruta': 'margen_bruto', 'resultado_antes_impuestos': 'resultado_antes_impuestos',
        'flujo_caja_antes_iva': 'flujo_total_pre_iva', 'iva_debito_neto': 'iva_debito_neto',
        'iva_credito': 'iva_credito_total', 'ventas_emitidas': 'documentos_emitidos',
        'unidades_emitidas': 'unidades_vendidas', 'depositos_netos': 'ingresos_bancarios_neto'}
    for month, expected in oracle['monthly'].items():
        selected = analyze_relational_ledger(frames, date_from=month + '-01', date_to=month)
        for key, reference in monthly_keys.items():
            check(month + '/' + key, selected.get('kpis', {}).get(key), expected.get(reference, 0))
    for year in sorted({month[:4] for month in oracle['monthly']}):
        selected = analyze_relational_ledger(frames, date_from=year + '-01-01', date_to=year + '-12-31')
        for key, reference in monthly_keys.items():
            expected = sum(row.get(reference, 0) for month, row in oracle['monthly'].items() if month.startswith(year))
            check(year + '/' + key, selected.get('kpis', {}).get(key), expected)
    stores = {row['id'].casefold(): row for row in report['sucursales']}
    for key, expected in oracle['stores'].items():
        actual = stores.get(key.casefold(), {})
        check(key + '/ventas', actual.get('ventas'), expected['ventas_brutas_netas'] - expected['devolucion_neta'])
        check(key + '/costo', actual.get('costo'), expected['costo_ventas_bruto'] - expected['costo_revertido_por_devolucion'])
    return {'total': len(checks), 'passed': sum(row['passed'] for row in checks), 'checks': checks}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('workbook', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--from-date')
    parser.add_argument('--to-date')
    parser.add_argument('--oracle', type=Path)
    parser.add_argument('--pipeline-focus', help='Run the automatic UI relationship flow, focused on a transaction-line sheet (e.g. DET_VENTAS, not its document header VENTAS).')
    args = parser.parse_args()
    content = args.workbook.read_bytes()
    started = time.perf_counter()
    loaded, _ = load_dataframes_with_reports(args.workbook.name, content, xlsx_sheet_names(content))
    frames = {name: _analyze_cached(args.workbook.name, content, {}, True, sheet=name,
        preloaded=source)['_df_limpio'] for name, source in loaded.items()}
    report = analyze_relational_ledger(frames, date_from=args.from_date, date_to=args.to_date)
    if args.pipeline_focus:
        profiles = next(iter(loaded.values()))[1]['clasificacion_hojas']
        manifest = {'hojas': [{'nombre': row['nombre'], 'procesar': row['clasificacion'] == 'datos',
            'mapping': {}, 'rules': {}, 'eliminar_duplicados': False} for row in profiles]}
        manifest = _parse_sheet_manifest(json.dumps(manifest))
        flow = _relationships_sync(args.workbook.name, content, manifest, focus={'sheets': [args.pipeline_focus]})
        metrics = flow.get('metrics') or {}
        BotRequest(message='Ventas netas', metrics=metrics)
        integration = (metrics.get('analisis_negocio') or {}).get('conciliacion')
        if not integration or integration.get('kpis') != report.get('kpis'):
            expected = report.get('kpis') or {}
            actual = (integration or {}).get('kpis') or {}
            diagnostic = {'available': (integration or {}).get('available'),
                          'warnings': (integration or {}).get('advertencias'),
                          'flow_warnings': metrics.get('advertencias'),
                          'differences': {key: {'expected': expected.get(key), 'actual': actual.get(key)}
                                          for key in expected.keys() | actual.keys() if expected.get(key) != actual.get(key)}}
            raise RuntimeError('Automatic UI relationship flow differs from the independently reconciled ledger: '
                               + json.dumps(diagnostic, ensure_ascii=False, default=str))
        catalog = _relationship_catalog_sync(args.workbook.name, content, manifest)
        dashboards = []
        for relationship in catalog.get('relationships', []):
            dashboard = _relationship_dashboard_sync(args.workbook.name, content, manifest, relationship, None, None)
            dashboards.append({'id': relationship['id'], 'available': dashboard.get('available'),
                'kpis': dashboard.get('kpis'), 'chart_count': len(dashboard.get('charts', []))})
            if not dashboard.get('available'):
                raise RuntimeError(f'Offered manual relationship has no dashboard: {relationship["id"]}')
        report['pipeline_validation'] = {'available': bool(integration and integration.get('available')),
            'income': (metrics.get('kpis', {}).get('ingresos_totales') or {}).get('valor'),
            'relationships': catalog.get('relationships', []),
            'manual_dashboards': dashboards,
            'processed_sheets': [row['nombre'] for row in manifest['hojas'] if row['procesar']]}
    if args.oracle and report and report['available']:
        report['validation'] = compare_oracle(frames, report, json.loads(args.oracle.read_text(encoding='utf-8-sig')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, default=str, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'seconds': round(time.perf_counter() - started, 2),
                     'available': report and report['available'],
                     'warnings': report and report['advertencias'], 'kpis': report and report.get('kpis')}, ensure_ascii=False))
    if report and 'validation' in report:
        validation = report['validation']
        print(json.dumps({**validation, 'checks': [row for row in validation['checks'] if not row['passed']]}))
        if validation['passed'] != validation['total']:
            raise SystemExit(1)
    if not report or not report['available']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
