"""Regression tests for the safe multi-sheet business model."""

import pandas as pd

from app.engine.business import (
    _cost_outlier_mask,
    analyze_business_workbook,
    classify_business_sheets,
)


def _sales_mapping() -> dict[str, dict[str, str]]:
    return {
        "Ventas_2026": {
            "fecha": "Fecha Venta",
            "monto": "Monto Venta",
            "cantidad": "Cantidad",
            "producto": "SKU Producto",
            "cliente": "ID Cliente",
        }
    }


def test_business_analysis_excludes_totals_and_cancelled_rows_and_uses_asof_cost():
    frames = {
        "Ventas_2026": pd.DataFrame(
            [
                {
                    "Fecha Venta": "01/01/2026",
                    "ID Documento": "D1",
                    "SKU Producto": "A",
                    "Cantidad": "2",
                    "Monto Venta": "200",
                    "Estado": "Vigente",
                    "ID Cliente": "C1",
                },
                {
                    "Fecha Venta": "02/01/2026",
                    "ID Documento": "D2",
                    "SKU Producto": "B",
                    "Cantidad": "1",
                    "Monto Venta": "150",
                    "Estado": "Anulado",
                    "ID Cliente": "C2",
                },
                {
                    "Fecha Venta": "",
                    "ID Documento": "TOTAL",
                    "SKU Producto": "",
                    "Cantidad": "3",
                    "Monto Venta": "350",
                    "Estado": "",
                    "ID Cliente": "",
                },
            ]
        ),
        "Historial_Costos": pd.DataFrame(
            [
                {"SKU Producto": "A", "Fecha Vigencia": "01/01/2025", "Costo Unitario": "40"},
                {"SKU Producto": "A", "Fecha Vigencia": "01/02/2026", "Costo Unitario": "70"},
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [{"SKU Producto": "A", "Costo Unitario": "90"}]
        ),
        "Gastos_Operacionales": pd.DataFrame(
            [{"Fecha Gasto": "15/01/2026", "Monto Neto": "30", "Tipo Gasto": "Fijo", "Estado": "Pagado"}]
        ),
        "Inventario": pd.DataFrame(
            [{"SKU Producto": "A", "Valor Inventario": "500"}]
        ),
        "Parametros": pd.DataFrame([{"Clave": "IVA", "Valor": "19"}]),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["alcance"]["filas_ventas_fisicas"] == 3
    assert result["alcance"]["filas_totales_estructurales"] == 1
    assert result["alcance"]["filas_anuladas"] == 1
    assert result["alcance"]["filas_indicadores"] == 1
    assert result["estado_resultados"]["ventas_observadas"] == 200
    # 2 unidades × costo histórico vigente de 40; nunca el costo actual de 90.
    assert result["estado_resultados"]["costo_venta_conocido"] == 80
    assert result["estado_resultados"]["utilidad_bruta"] == 120
    assert result["estado_resultados"]["resultado_operacional"] == 90
    assert "Parametros" not in result["alcance"]["hojas_utilizadas"]


def test_products_sheet_without_costo_in_its_name_is_still_used_as_cost_source():
    """Regresión QA: una PyME chica suele tener un solo "Productos" con ID,
    categoria y Costo_Unitario en la misma hoja, sin nombrarla "Costos_...".
    classify_business_sheets la clasificaba como "productos" (por el nombre
    de la hoja) y el motor nunca la usaba como fuente de costo, aunque traía
    un costo unitario real por SKU -- la cobertura de costos quedaba en 0%
    pese a que el cruce por ID_Producto era perfecto."""
    frames = {
        "Ventas": pd.DataFrame(
            [
                {"ID_Producto": "P-001", "Cantidad": "2", "Monto": "200", "Fecha": "01/01/2026"},
                {"ID_Producto": "P-002", "Cantidad": "1", "Monto": "150", "Fecha": "02/01/2026"},
            ]
        ),
        "Productos": pd.DataFrame(
            [
                {"ID_Producto": "P-001", "Producto": "Audifonos", "Costo_Unitario": "40"},
                {"ID_Producto": "P-002", "Producto": "Mouse", "Costo_Unitario": "70"},
            ]
        ),
    }
    mapping = {
        "Ventas": {
            "fecha": "Fecha",
            "monto": "Monto",
            "cantidad": "Cantidad",
            "producto": "ID_Producto",
        }
    }

    result = analyze_business_workbook(frames, mapping, {})

    assert result is not None
    assert result["alcance"]["hoja_costos"] == "Productos"
    assert result["estado_resultados"]["cobertura_costos_pct"] == 100
    # 2×40 + 1×70
    assert result["estado_resultados"]["costo_venta_conocido"] == 150
    assert result["estado_resultados"]["utilidad_bruta"] == 200


def test_document_duplicates_split_into_identical_conflict_and_observation_only():
    """Regresión QA (auditoría externa): un ID de documento repetido debe
    clasificarse en exactamente una de tres categorías -- conflicto real de
    negocio, copia idéntica, o solo difiere en una columna Observación.* --
    expuestas por separado. Antes solo se exponía el total agregado de
    repetidos y de conflictivos, mezclando copias idénticas con diferencias
    de Observación dentro del mismo resto sin desglosar."""
    frames = {
        "Ventas": pd.DataFrame(
            [
                # D1: copia idéntica exacta (incluye Observación.1 igual).
                {"ID Documento": "D1", "Fecha": "01/01/2026", "Monto": "100", "Observación.1": "nota"},
                {"ID Documento": "D1", "Fecha": "01/01/2026", "Monto": "100", "Observación.1": "nota"},
                # D2: solo difiere en Observación.1 -- no es conflicto real.
                {"ID Documento": "D2", "Fecha": "02/01/2026", "Monto": "200", "Observación.1": "nota A"},
                {"ID Documento": "D2", "Fecha": "02/01/2026", "Monto": "200", "Observación.1": "nota B"},
                # D3: conflicto real -- el Monto difiere.
                {"ID Documento": "D3", "Fecha": "03/01/2026", "Monto": "300", "Observación.1": "nota"},
                {"ID Documento": "D3", "Fecha": "03/01/2026", "Monto": "999", "Observación.1": "nota"},
            ]
        )
    }
    mapping = {"Ventas": {"fecha": "Fecha", "monto": "Monto"}}

    result = analyze_business_workbook(frames, mapping, {})

    assert result is not None
    alcance = result["alcance"]
    assert alcance["documentos_repetidos"] == 3
    assert alcance["documentos_conflictivos"] == 1
    assert alcance["documentos_identicos"] == 1
    assert alcance["documentos_solo_observacion_distinta"] == 1


def test_attribute_conflicts_never_inflate_referencias_problematicas():
    """Regresión P1-8: un SKU que SÍ existe en el maestro pero con un nombre
    distinto es un conflicto de ATRIBUTO, no una referencia huérfana. Antes,
    _attribute_consistency reutilizaba el campo "huerfanas" para contar
    conflictos de nombre, y ese número se sumaba al total agregado
    referencias_problematicas -- una clave perfectamente válida inflaba la
    cifra que el usuario lee como "referencias sin correspondencia"."""
    frames = {
        "Ventas": pd.DataFrame(
            [
                {"ID_Producto": "P-001", "Producto": "Nombre Incorrecto", "Monto": "100", "Fecha": "01/01/2026"},
                {"ID_Producto": "P-001", "Producto": "Nombre Incorrecto", "Monto": "200", "Fecha": "02/01/2026"},
            ]
        ),
        "Productos": pd.DataFrame(
            [{"ID_Producto": "P-001", "Producto": "Nombre Correcto", "Costo_Unitario": "50"}]
        ),
    }
    mapping = {"Ventas": {"fecha": "Fecha", "monto": "Monto"}}

    result = analyze_business_workbook(frames, mapping, {})

    assert result is not None
    integrity = result["calidad"]["integridad_referencial"]
    attr_entry = next(item for item in integrity if item["tipo"] == "atributo")
    assert attr_entry["conflictos"] == 2
    assert attr_entry["huerfanas"] == 0
    # La clave SÍ existe -- 0 referencias problemáticas, no 2.
    assert result["calidad"]["referencias_problematicas"] == 0


def test_products_relation_recognizes_id_producto_key_not_only_sku():
    """Regresión P1-8: product_ref_key (usado en "Ventas → Productos" y su
    verificación de nombre) solo buscaba el patrón "sku"+"producto" -- un
    maestro de productos con clave "ID_Producto" (el patrón más común visto
    en los archivos de prueba de esta sesión) nunca generaba esas dos
    entradas de integridad referencial, aunque el cruce fuera perfecto."""
    frames = {
        "Ventas": pd.DataFrame(
            [{"ID_Producto": "P-001", "Producto": "Correcto", "Monto": "100", "Fecha": "01/01/2026"}]
        ),
        "Productos": pd.DataFrame([{"ID_Producto": "P-001", "Producto": "Correcto"}]),
    }
    mapping = {"Ventas": {"fecha": "Fecha", "monto": "Monto"}}

    result = analyze_business_workbook(frames, mapping, {})

    assert result is not None
    relations = {item["relacion"] for item in result["calidad"]["integridad_referencial"]}
    assert "Ventas → Productos" in relations
    assert "Ventas → Productos (nombre)" in relations


def test_duplicated_master_key_is_reported_separately_from_conflict():
    """Regresión P1-8: un maestro con la misma clave repetida hace que la
    fila usada como referencia sea arbitraria (keep="first"). Se informa
    aparte según si los valores repetidos coinciden (maestro_duplicado) o
    realmente difieren entre sí (maestro_conflictivo, subconjunto)."""
    from app.engine.business import _attribute_consistency

    ventas = pd.DataFrame(
        {"SKU": ["A", "B"], "Nombre": ["Widget", "Gadget"]}
    )
    # A: duplicado pero con el MISMO nombre -- no es conflictivo.
    # B: duplicado con nombres DISTINTOS -- sí es conflictivo.
    maestro = pd.DataFrame(
        {
            "SKU": ["A", "A", "B", "B"],
            "Nombre": ["Widget", "Widget", "Gadget", "Artilugio"],
        }
    )
    res = _attribute_consistency(ventas, "SKU", "Nombre", maestro, "SKU", "Nombre", "V-M")
    assert res["maestro_duplicado"] == 2  # A y B están duplicados
    assert res["maestro_conflictivo"] == 1  # solo B tiene valores distintos


def test_current_catalogue_fills_history_gaps_without_certifying_the_estimate():
    frames = {
        "Ventas_2024": pd.DataFrame(
            [
                {
                    "Fecha Venta": "01/01/2024",
                    "ID Documento": "D1",
                    "SKU Producto": "A",
                    "Cantidad": "2",
                    "Monto Venta": "200",
                    "Estado": "Vigente",
                }
            ]
        ),
        "Historial_Costos": pd.DataFrame(
            [
                {
                    "SKU Producto": "A",
                    "Fecha Vigencia": "01/01/2025",
                    "Costo Unitario": "40",
                }
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [{"SKU Producto": "A", "Costo Unitario": "50"}]
        ),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["estado_resultados"]["cobertura_costos_pct"] == 100
    assert result["estado_resultados"]["costo_venta_conocido"] == 100
    assert result["estado_resultados"]["cobertura_costos_certificable_pct"] == 0
    assert result["estado_resultados"]["utilidad_certificable"] is None
    assert result["calidad"]["costos"]["filas_costo_actual_estimado"] == 1


def test_certifiable_sales_keep_one_exact_copy_and_exclude_conflicting_ids():
    base = {
        "Fecha Venta": "01/01/2026",
        "SKU Producto": "A",
        "Cantidad": "1",
        "Monto Venta": "100",
        "Estado": "Vigente",
    }
    frames = {
        "Ventas_2026": pd.DataFrame(
            [
                {**base, "ID Documento": "EXACTO"},
                {**base, "ID Documento": "EXACTO"},
                {**base, "ID Documento": "CONFLICTO"},
                {**base, "ID Documento": "CONFLICTO", "Monto Venta": "150"},
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [{"SKU Producto": "A", "Costo Unitario": "40"}]
        ),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["estado_resultados"]["ventas_observadas"] == 450
    assert result["estado_resultados"]["ventas_certificables"] == 100
    assert result["alcance"]["documentos_repetidos"] == 2
    assert result["alcance"]["filas_adicionales_documento"] == 2
    assert result["alcance"]["documentos_conflictivos"] == 1


def test_business_analysis_preaggregates_collections_and_excludes_exact_payment_duplicates():
    frames = {
        "Ventas_2026": pd.DataFrame(
            [
                {
                    "Fecha Venta": "01/01/2026",
                    "ID Documento": "D1",
                    "SKU Producto": "A",
                    "Cantidad": "1",
                    "Monto Venta": "100",
                    "Total Documento": "119",
                    "Estado": "Vigente",
                    "ID Cliente": "C1",
                }
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [{"SKU Producto": "A", "Costo Unitario": "50"}]
        ),
        "Cobranzas": pd.DataFrame(
            [
                {"ID Pago": "P1", "ID Documento": "D1", "Monto Pago": "60", "Estado Pago": "Aplicado", "Fecha Pago": "02/01/2026"},
                {"ID Pago": "P1", "ID Documento": "D1", "Monto Pago": "60", "Estado Pago": "Aplicado", "Fecha Pago": "02/01/2026"},
                {"ID Pago": "P2", "ID Documento": "D1", "Monto Pago": "59", "Estado Pago": "Aplicado", "Fecha Pago": "03/01/2026"},
            ]
        ),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["operacion"]["cobrado_aplicado"] == 119
    assert result["operacion"]["pagos_duplicados_excluidos"] == 1
    assert result["operacion"]["documentos_sobrepagados"] == 0
    assert result["operacion"]["cobranza_sobre_documentos_pct"] == 100


def test_business_analysis_does_not_treat_credit_notes_as_overpaid_receivables():
    frames = {
        "Ventas_2026": pd.DataFrame(
            [
                {
                    "Fecha Venta": "01/01/2026",
                    "ID Documento": "F1",
                    "Tipo Documento": "Factura",
                    "SKU Producto": "A",
                    "Cantidad": "1",
                    "Monto Venta": "100",
                    "Total Documento": "119",
                    "Estado": "Vigente",
                },
                {
                    "Fecha Venta": "02/01/2026",
                    "ID Documento": "NC1",
                    "Tipo Documento": "Nota de Credito",
                    "SKU Producto": "A",
                    "Cantidad": "-1",
                    "Monto Venta": "-100",
                    "Total Documento": "-119",
                    "Estado": "Vigente",
                },
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [{"SKU Producto": "A", "Costo Unitario": "50"}]
        ),
        "Cobranzas": pd.DataFrame(
            [
                {
                    "ID Pago": "P1",
                    "ID Documento": "F1",
                    "Monto Pago": "119",
                    "Estado Pago": "Aplicado",
                    "Fecha Pago": "03/01/2026",
                }
            ]
        ),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["operacion"]["documentos_sobrepagados"] == 0
    assert result["operacion"]["cobranza_sobre_documentos_pct"] == 100


def test_conflicting_cost_master_never_multiplies_sales_or_invents_margin():
    frames = {
        "Ventas_2026": pd.DataFrame(
            [
                {
                    "Fecha Venta": "01/01/2026",
                    "ID Documento": "D1",
                    "SKU Producto": "A",
                    "Cantidad": "2",
                    "Monto Venta": "200",
                    "Estado": "Vigente",
                    "ID Cliente": "C1",
                }
            ]
        ),
        "Costos_Productos": pd.DataFrame(
            [
                {"SKU Producto": "A", "Costo Unitario": "40"},
                {"SKU Producto": "A", "Costo Unitario": "90"},
            ]
        ),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    assert result["estado_resultados"]["ventas_observadas"] == 200
    assert result["estado_resultados"]["cobertura_costos_pct"] == 0
    assert result["estado_resultados"]["utilidad_bruta"] is None
    assert result["calidad"]["costos"]["conflictivas"] == 1
    assert result["estado_certificacion"] == "blocked"


def test_inventory_is_not_misclassified_as_sales_and_unsupported_ratios_stay_unavailable():
    frames = {
        "Ventas_2026": pd.DataFrame(
            [{"Fecha Venta": "01/01/2026", "ID Documento": "D1", "SKU Producto": "A", "Cantidad": "1", "Monto Venta": "100", "Estado": "Vigente"}]
        ),
        "Inventario": pd.DataFrame(
            [{"SKU Producto": "A", "Stock Sistema": "3", "Valor Inventario": "120"}]
        ),
    }

    kinds = classify_business_sheets(frames)
    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert kinds["ventas"] == ["Ventas_2026"]
    assert kinds["inventario"] == ["Inventario"]
    assert result is not None
    unavailable = {
        ratio["id"]: ratio["estado"]
        for ratio in result["ratios"]
        if ratio["id"] in {"liquidez_corriente", "prueba_acida", "roe", "roa", "ebitda"}
    }
    assert unavailable == {
        "liquidez_corriente": "unavailable",
        "prueba_acida": "unavailable",
        "roe": "unavailable",
        "roa": "unavailable",
        "ebitda": "unavailable",
    }


def test_cost_outlier_mask_uses_category_limit_that_global_comparison_would_miss():
    """Regresión QA P1-6: un costo alto en una categoria barata (ej. un
    insumo de aseo a 200 cuando el resto de aseo cuesta 40-59) es un
    verdadero atipico que alguien deberia revisar. Comparado contra el
    catalogo COMPLETO -- que incluye una categoria de precio base muy
    distinto (electronica a 900-919) -- el mismo valor pasa piola porque
    el limite global queda inflado por esa otra categoria. El analisis
    por categoria debe detectarlo igual; el global-only, no."""
    aseo_values = list(range(40, 60)) + [200]
    electronica_values = list(range(900, 920))
    values = pd.Series(aseo_values + electronica_values, dtype=float)
    groups = pd.Series(["Aseo"] * len(aseo_values) + ["Electronica"] * len(electronica_values))

    global_mask = _cost_outlier_mask(values)
    category_mask = _cost_outlier_mask(values, groups)

    outlier_index = aseo_values.index(200)
    assert not global_mask.iloc[outlier_index]
    assert category_mask.iloc[outlier_index]
    # Ningun valor normal de ninguna categoria queda marcado.
    assert category_mask.sum() == 1


def test_cost_outlier_mask_falls_back_to_global_limit_for_small_groups():
    """Un grupo con pocas filas (< 20) no tiene evidencia propia para su
    propio limite -- debe evaluarse igual usando el limite global en vez
    de quedar sin evaluar por pertenecer a una categoria chica."""
    common_values = list(range(40, 65))  # 25 valores, categoria con evidencia propia
    small_group_values = [41, 5000]  # categoria con solo 2 filas
    values = pd.Series(common_values + small_group_values, dtype=float)
    groups = pd.Series(["Comun"] * len(common_values) + ["Chica"] * len(small_group_values))

    mask = _cost_outlier_mask(values, groups)

    assert not mask.iloc[len(common_values)]  # 41 en la categoria chica: no es atipico
    assert mask.iloc[len(common_values) + 1]  # 5000 en la categoria chica: si lo es


def test_cost_outlier_mask_never_reduces_to_empty_when_no_groups_given():
    values = pd.Series(list(range(40, 61)) + [5000], dtype=float)

    mask = _cost_outlier_mask(values)

    assert mask.sum() == 1
    assert mask.iloc[-1]


def _sales_frame_for_products(product_ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Fecha Venta": "01/01/2026",
                "ID Documento": f"D{i}",
                "SKU Producto": product_id,
                "Cantidad": "1",
                "Monto Venta": "1000",
                "Estado": "Vigente",
                "ID Cliente": "C1",
            }
            for i, product_id in enumerate(product_ids)
        ]
    )


def test_atypical_cost_is_never_excluded_from_official_profit_but_is_reported_separately():
    """Regresion QA P1-6: antes, un costo atipico del catalogo quedaba
    fuera del lookup (`trustworthy &= current_values.le(limit)`) y la
    venta pareada perdia su costo real sin avisar. Ahora el costo real
    SIEMPRE se usa en el resultado oficial; solo se marca aparte y se
    informa cuanto pesaria si se excluyera."""
    # Necesitan variacion real (no todos el mismo valor) para que el IQR
    # tenga un spread > 0 y pueda calcular un limite.
    normal_products = [f"P{i:03d}" for i in range(21)]
    normal_rows = [
        {"SKU Producto": pid, "Costo Unitario": str(40 + i)} for i, pid in enumerate(normal_products)
    ]
    outlier_row = [{"SKU Producto": "P-OUT", "Costo Unitario": "5000"}]

    frames = {
        "Ventas_2026": _sales_frame_for_products(normal_products + ["P-OUT"]),
        "Costos_Productos": pd.DataFrame(normal_rows + outlier_row),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    costos = result["calidad"]["costos"]
    assert costos["extremos"] >= 1
    assert costos["analisis_por_categoria"] is False

    normal_cost_total = sum(40 + i for i in range(21))
    # El costo atipico real (5000) sigue sumado en el resultado oficial.
    assert result["estado_resultados"]["costo_venta_conocido"] == normal_cost_total + 5000

    escenario = costos["escenario_sin_atipicos"]
    assert escenario["estado_revision"] == "requiere_revision"
    assert escenario["monto_costo_atipico_incluido"] == 5000
    # Sin el atipico se excluye TODA la fila (venta 1000 + costo 5000): la
    # utilidad pareada sube en el neto, 5000 - 1000 = 4000.
    assert escenario["utilidad_bruta"] == result["estado_resultados"]["utilidad_bruta"] + 4000

    decision_titles = [d["titulo"] for d in result["decisiones"]]
    assert "Validar costos que distorsionan el margen" in decision_titles
    flagged_decision = next(
        d for d in result["decisiones"] if d["titulo"] == "Validar costos que distorsionan el margen"
    )
    assert "5000" in flagged_decision["evidencia"]


def test_cost_quality_uses_category_column_when_catalogue_provides_one():
    """Con columna de categoria en el catalogo de costos, el motor debe
    compararlos POR CATEGORIA (no todos contra todos) y exponerlo via
    `analisis_por_categoria`."""
    aseo_products = [f"AS{i:03d}" for i in range(20)]
    aseo_rows = [
        {"SKU Producto": pid, "Categoria": "Aseo", "Costo Unitario": str(40 + i)}
        for i, pid in enumerate(aseo_products)
    ]
    electronica_products = [f"EL{i:03d}" for i in range(20)]
    electronica_rows = [
        {"SKU Producto": pid, "Categoria": "Electronica", "Costo Unitario": str(900 + i)}
        for i, pid in enumerate(electronica_products)
    ]
    outlier_row = [{"SKU Producto": "AS-OUT", "Categoria": "Aseo", "Costo Unitario": "200"}]

    frames = {
        "Ventas_2026": _sales_frame_for_products(aseo_products + electronica_products + ["AS-OUT"]),
        "Costos_Productos": pd.DataFrame(aseo_rows + electronica_rows + outlier_row),
    }

    result = analyze_business_workbook(frames, _sales_mapping(), {})

    assert result is not None
    costos = result["calidad"]["costos"]
    assert costos["analisis_por_categoria"] is True
    # El atipico de Aseo (200 entre 40-59) se detecta pese a que Electronica
    # (900-919) opaca esa diferencia si se comparara todo junto.
    assert costos["extremos"] >= 1
    assert costos["escenario_sin_atipicos"]["monto_costo_atipico_incluido"] == 200
