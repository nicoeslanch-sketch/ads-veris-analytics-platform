"""Synthetic, independently checkable conversations; no customer data."""

from copy import deepcopy


def sales_metrics():
    return {
        "moneda": "CLP", "calidad_datos": 95,
        "periodo": {"desde": "2026-01-01", "hasta": "2026-03-31"},
        "kpis": {"ingresos_totales": {"valor": 600}, "transacciones": 6,
                 "ticket_promedio": 100, "ganancia_neta": None},
        "evolucion_mensual": [{"mes": "2026-01", "ingresos": 100},
                             {"mes": "2026-02", "ingresos": 200},
                             {"mes": "2026-03", "ingresos": 300}],
        "ventas_por_canal": [{"nombre": "Norte", "ingresos": 400},
                             {"nombre": "Sur", "ingresos": 200}],
        "agrupado_por_canal": "sucursal",
        "por_categoria": [{"nombre": "Alimentos", "ingresos": 350},
                          {"nombre": "Hogar", "ingresos": 250}],
        "top_productos": [{"nombre": "Producto Azul", "ingresos": 400},
                          {"nombre": "Producto Verde", "ingresos": 200}],
        "clientes": {"unicos": 4, "top": [{"nombre": "Cliente A", "ingresos": 400}]},
        "duplicados": {"detectados": 1, "eliminados": 0, "conservados": 1},
        "advertencias": ["No hay costos atribuibles completos."],
    }


def conversation_scenarios():
    sales = sales_metrics()
    years = deepcopy(sales)
    years["evolucion_mensual"].insert(0, {"mes": "2025-01", "ingresos": 50})
    zero = deepcopy(sales)
    zero["evolucion_mensual"][0]["ingresos"] = 0
    partial = deepcopy(sales)
    partial["evolucion_mensual"][2]["parcial"] = True
    uf = deepcopy(sales)
    uf["moneda"] = "UF"
    catalog = {'tipo_analisis': 'catalogo_productos', 'moneda': 'CLP', 'kpis': {},
               'analisis_productos': {'productos': 4, 'registros': 5, 'activos': 2,
                                     'inactivos': 1, 'sin_estado': 2,
                                     'costos': {'promedio': 220}, 'precios_lista': {'promedio': 440}}}
    return [
        ('catalog_status_followups', catalog, [
            ('cuantosproductos tengo', ['4 productos']),
            ('y cuantos estan inactvos', ['1 registro inactivo', 'por fila']),
            ('que porcentaje representa eso', ['20%', '5 registros']),
            ('y los activos', ['2 registros activos']),
            ('que porcentaje representan', ['40%', '5 registros']),
            ('y los activos en enero', ['No tengo publicado']),
            ('y los inactivos', ['No tengo publicado']),
            ('estado del catalogo en general', ['2 registros activos', '1 registro inactivo']),
            ('entonces debo dejar de comprar esos productos', ['no justifica', 'ventas por ID', 'stock disponible']),
            ('inactivos de Hogar', ['No tengo publicado']),
            ('que porcentaje representa eso', ['No tengo publicado']),
            ('esta activo el producto Uno', ['No tengo publicado']),
        ]),
        ("retained_month_scope", sales, [
            ("cuanto vendi en enero", ["2026-01", "$100"]),
            ("y cuantos clientes tuve", ["no", "cruce"]),
            ("y el ticket promedio", ["no", "medida"]),
            ("y cuanto gane", ["no", "medida"]),
            ("mis ingresos del total general", ["$600"]),
        ]),
        ("retained_expense_measure", sales, [
            ("cuanto gaste en enero", ["no", "medida"]),
            ("y en febrero", ["no", "medida"]),
            ("y en marzo", ["no", "medida"]),
            ("cuanto vendi en marzo", ["$300"]),
        ]),
        ("retained_segment_scope", sales, [
            ("cuanto vendi en la sucursal Sur", ["La sucursal consultada", "$200"]),
            ("y cual es el producto mas vendido", ["no", "cruce"]),
            ("y el ticket promedio", ["no", "medida"]),
            ("y el margen", ["no", "medida"]),
            ("cual es el producto mas vendido en general", ["Producto Azul", "$400"]),
        ]),
        ("monthly_shares", sales, [
            ("que porcentaje aporta febrero", ["33,3%", "$200 / $600", "denominador"]),
            ("y marzo", ["50%", "$300 / $600"]),
            ("y enero", ["16,7%", "$100 / $600"]),
        ]),
        ("reset_scope", sales, [
            ("cuanto vendi en enero", ["2026-01", "$100"]),
            ("ahora el total general", ["$600"]),
            ("y cuantos clientes tengo", ["4 clientes"]),
            ("cuanto vendi en febrero", ["$200"]),
            ("como descargo el archivo", ["descarg"]),
            ("y cuantos clientes tengo", ["4 clientes"]),
        ]),
        ("decisions_not_account_actions", sales, [
            ("deberia cerrar mi empresa", ["continuidad", "caja", "no bastan"]),
            ("cual es el producto mas rentable", ["costos", "ranking", "no"]),
            ("cuanto vendere el proximo mes", ["No puedo conocer", "supuestos"]),
            ("si mis ingresos suben un 20% cuanto tendria", ["hipotetico", "simulacion"]),
        ]),
        ("monthly_followups", sales, [
            ("cuanto vendi en enero", ["2026-01", "$100"]),
            ("y en febrero?", ["2026-02", "$200"]),
            ("compara enero con febrero", ["$100", "$200", "100%"]),
            ("cuanto vendi en 2025", ["no", "2025"]),
        ]),
        ("monthly_direction", sales, [
            ("cuanto crecieron mis ingresos de marzo a enero", ["$300", "$100", "66,7%"]),
            ("cuanto vendi entre enero y marzo", ["$600", "3"]),
            ("que mes vendi mas", ["2026-03", "$300"]),
            ("y el peor", ["2026-01", "$100"]),
        ]),
        ("ambiguous_year", years, [
            ("cuanto vendi en enero", ["2025-01", "2026-01", "cual"]),
            ("2026", ["2026-01", "$100"]),
        ]),
        ("missing_period", sales, [
            ("cuanto vendi en diciembre de 2024", ["no", "2024-12"]),
            ("cuanto vendi el 15 de enero", ["diario", "no"]),
        ]),
        ("zero_baseline", zero, [
            ("compara enero con febrero", ["$0", "$200", "porcentual", "cero"]),
        ]),
        ("partial_month", partial, [
            ("compara febrero con marzo", ["$200", "$300", "parcial"]),
        ]),
        ("named_segments", sales, [
            ("cuanto vendi en la sucursal Sur", ["Sur", "$200"]),
            ("y Norte?", ["Norte", "$400"]),
            ("compara Norte y Sur", ["Norte", "Sur", "$200"]),
            ("cuanto vendi en la sucursal Fantasma", ["no", "Fantasma"]),
        ]),
        ("no_cross_tab_invention", sales, [
            ("cuanto vendi en Sur durante enero", ["cruce", "no"]),
        ]),
        ("compound_questions", sales, [
            ("cuantos ingresos tengo y cuantos clientes tengo", ["$600", "4 clientes"]),
            ("cuanto gane? cuantos duplicados hay?", ["costo", "1 duplicados"]),
        ]),
        ("courtesy_and_correction", sales, [
            ("gracias, y cuantos clientes tengo?", ["4 clientes"]),
            ("no me refiero a ingresos, sino al margen", ["margen", "no"]),
        ]),
        ("unit_and_scope", uf, [
            ("cuanto vendi en febrero", ["UF 200"]),
            ("y en marzo?", ["UF 300"]),
            ("convierte mis ingresos a pesos", ["tipo de cambio", "fecha"]),
        ]),
        ("no_context", None, [
            ("cuantos ingresos tengo", ["archivo", "no"]),
            ("y el mejor?", ["indicador"]),
            ("hola", ["Hola"]),
        ]),
        ("misspelled_periods", sales, [
            ("cuantovendienenero", ["2026-01", "$100"]),
            ("cuanto vendi en enreo", ["2026-01", "$100"]),
            ("y en febreo", ["2026-02", "$200"]),
            ("y en marso", ["2026-03", "$300"]),
            ("cuanto vendi desde enero hasta marzo", ["$600", "3 meses"]),
        ]),
        ("daily_formats", sales, [
            ("cuanto vendi el 15/01/2026", ["diario", "no"]),
            ("cuanto vendi el 15-01-2026", ["diario", "no"]),
            ("cuanto vendi el 2026-01-15", ["diario", "no"]),
            ("cuanto vendi en 2026-02", ["$200", "2026-02"]),
        ]),
        ("different_measures", sales, [
            ("cuanto gaste en enero", ["no", "medida", "ingresos"]),
            ("cual fue mi margen en febrero", ["no", "medida"]),
            ("cuantos clientes tuve en marzo", ["no", "cruce"]),
            ("cuanto fue mi IVA en enero", ["no", "medida"]),
            ("cuantas unidades vendi en febrero", ["no", "medida"]),
            ("cuanto vendi neto en enero", ["no", "medida"]),
        ]),
        ("unsupported_scopes", sales, [
            ("cuanto vendi hoy", ["filtro", "no"]),
            ("cuanto vendi ayer", ["filtro", "no"]),
            ("cuanto vendi el trimestre pasado", ["filtro", "no"]),
            ("cuanto vendi la semana pasada", ["filtro", "no"]),
            ("cuanto vendi en Producto Azul en Sur", ["cruce", "no"]),
            ("compara Producto Azul en Sur", ["cruce", "no"]),
            ("cuanto vendi en Atlantis", ["no", "filtro"]),
        ]),
        ("long_business_conversation", sales, [
            ("hola, cuanto vendi", ["$600"]),
            ("y cuantas transacciones", ["6"]),
            ("y el ticket promedio", ["$100"]),
            ("y cuantos clientes tengo", ["4"]),
            ("cual es mi producto principal", ["Producto Azul", "$400"]),
            ("y el segundo producto", ["Producto Verde", "$200"]),
            ("compara Producto Azul y Producto Verde", ["$400", "$200"]),
            ("cuantos duplicados hay", ["1 duplicados", "eliminaron 0"]),
            ("que calidad tienen mis datos", ["95"]),
            ("cuanto vendi en enero", ["$100"]),
            ("y en febrero", ["$200"]),
            ("y en marzo", ["$300"]),
            ("y en diciembre", ["no", "diciembre"]),
            ("cual es mi moneda", ["CLP"]),
            ("cuanto gane realmente", ["no", "costo"]),
            ("no hablo de ganancia sino de ingresos", ["$600"]),
            ("gracias, y cuantos clientes tengo", ["4"]),
            ("dame una conclusion general", ["$600", "costos"]),
        ]),
        ("platform_support", None, [
            ("como conecto Google Sheets", ["Google", "Sheets"]),
            ("como descargo los datos limpios", ["descarg"]),
            ("porquedemoralalimpieza", ["limpieza"]),
            ("nosepudoconectaralservidor", ["servidor"]),
            ("que diferencia hay entre resumen y explorar", ["Resumen", "Explorar"]),
            ("que son los ADS Coins", ["Coins"]),
            ("puedo hablar con soporte humano", ["Ayuda", "conversa"]),
            ("que es estandarizacion", ["estandar"]),
            ("como conecto hojas por ID", ["ID"]),
            ("como detectas duplicados", ["duplicado"]),
        ]),
        ("scope_continuation", sales, [
            ("cuanto vendi en la sucursal Sur", ["$200", "Sur"]),
            ("y en febrero?", ["no", "cruce"]),
            ("cuanto vendi en febrero sin devoluciones", ["no", "subtotal"]),
            ("cuantas unidades vendi en Sur", ["no", "medida"]),
            ("cuantos ingresos tuvo el cliente Cliente B", ["no", "Cliente B"]),
        ]),
        ("production_followups", sales, [
            ("hola, cuantosingresos tengo?", ["$600"]),
            ("y esos ingresos son ganancias o plata cobrada?", ["No son equivalentes", "pagos recibidos", "costos"]),
            ("y en que moneda estan? son UF?", ["CLP", "pesos chilenos"]),
            ("si conservo los duplicados puedo descargar igual?", ["descargar conservando", "confirmas"]),
        ]),
    ]
