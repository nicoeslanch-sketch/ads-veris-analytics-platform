import pytest


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("cuantossonmisingresostotales", "cuantos son mis ingresos totales"),
        ("cuantossonmisingresostotlales", "cuantos son mis ingresos totales"),
        ("¿Cuatnos ingrseos ttales tengo?", "cuantos ingresos totales tengo"),
        ("flujodecaja", "flujo de caja"),
        ("partisipacionencobranzaporequipo", "participacion en cobranza por equipo"),
        ("¿La rentavilidad es vuena?", "la rentabilidad es buena"),
        ("analisishorizontal", "analisis horizontal"),
        ("pruebaacida", "prueba acida"),
        ("estadodeflujodeefectivo", "estado de flujo de efectivo"),
        ("decsargar el exel linpio", "descargar el excel limpio"),
        ("EST. JURIDICO LEXCO", "est juridico lexco"),
    ],
)
def test_query_normalization_tolerates_typos_and_joined_words(raw, expected):
    from app.language_normalization import normalize_query

    assert normalize_query(raw) == expected


@pytest.mark.parametrize(
    ("question", "matched_key", "expected"),
    [
        ("flujodecajaoperativo", "operating_cashflow", "antes de préstamos"),
        ("¿Cómo preparo un flijo de caha?", "cashflow_structure", "saldo inicial"),
        ("¿Qué muestra el balanse general?", "balance_sheet", "activos = pasivos + patrimonio"),
        ("¿Qué es el estadoderesultados?", "income_statement", "devengados"),
        ("¿Qué estadosfinancieros necesito?", "financial_statements_set", "estado de situación financiera"),
        ("¿Cómo interpreto la liquides?", "liquidity_reading", "no garantiza caja"),
        ("¿Qué es el ratio de efetivo?", "cash_ratio", "efectivo y equivalentes"),
        ("¿Cómo proyecto la caha mensualmente?", "cashflow_projection", "fechas reales de cobro y pago"),
        ("¿Qué hago si tendré deficitdecaja?", "cashflow_shortfall", "Un préstamo mejora caja inmediata"),
        ("¿Cómo reviso mi endeudamieno patrimonial?", "debt_structure", "deuda sobre activos"),
        ("¿Qué es el valordeldineroeneltiempo?", "time_value", "valor presente"),
        ("¿Diferencia entre interes simple y compuesto?", "simple_compound_interest", "capital inicial"),
        ("¿Cómo armo estadosfinancierosproyectados?", "projected_statements", "no son hechos"),
        ("¿Cuál es el orden para analizar estados financieros?", "financial_analysis_process", "análisis vertical y horizontal"),
    ],
)
def test_financial_documents_expand_the_bot_repertoire(question, matched_key, expected):
    from app.support_knowledge import answer_for

    answer = answer_for(question)

    assert answer["matched_key"] == matched_key
    assert expected in answer["answer"]


def test_financial_follow_up_keeps_the_previous_topic():
    from app.support_knowledge import answer_for

    answer = answer_for(
        "¿Y cómo lo interpreto?",
        history=[
            {"role": "user", "content": "¿Qué es la liquidez corriente?"},
            {"role": "assistant", "content": "Respuesta anterior"},
        ],
    )

    assert answer["matched_key"] in {"current_ratio", "liquidity_reading"}
    assert "liquidez" in answer["answer"].lower()


@pytest.mark.parametrize(
    ("previous", "follow_up", "matched_key"),
    [
        ("¿Qué es el ratio de efectivo?", "¿Qué datos necesito para calcularlos?", "cash_ratio"),
        ("¿Cómo reviso mi endeudamiento?", "¿Eso es malo?", "debt_ratio"),
        ("¿Cómo entra el flujo de caja?", "¿Cómo lo proyecto?", "cashflow_projection"),
        ("¿Qué estados financieros necesito?", "¿En qué orden?", "financial_analysis_process"),
    ],
)
def test_financial_follow_ups_resolve_short_references(previous, follow_up, matched_key):
    from app.support_knowledge import answer_for

    answer = answer_for(
        follow_up,
        history=[
            {"role": "user", "content": previous},
            {"role": "assistant", "content": "Respuesta anterior"},
        ],
    )

    assert answer["matched_key"] == matched_key


@pytest.mark.parametrize(
    ("question", "matched_key"),
    [
        ("¿Qué presupuestos necesito?", "projection_inputs"),
        ("¿Qué pasa si el saldo queda negativo?", "cashflow_shortfall"),
        ("¿Y si pido un préstamo?", "cashflow_shortfall"),
        ("¿Cómo cierro el análisis?", "financial_analysis_process"),
    ],
)
def test_financial_bot_handles_more_natural_business_questions(question, matched_key):
    from app.support_knowledge import answer_for

    assert answer_for(question)["matched_key"] == matched_key


@pytest.mark.parametrize(
    "question",
    [
        "cuantossonmisingresostotales",
        "¿Cuatnos ingrseos ttales tengo?",
        "¿Cuál fue mi ingreso toatl?",
        "dime mis ingrezos",
    ],
)
def test_metric_bot_understands_misspelled_income_questions(question):
    from app.metric_assistant import answer_metrics_question

    answer = answer_metrics_question(
        question,
        {"moneda": "CLP", "kpis": {"ingresos_totales": {"valor": 669700}}},
    )

    assert answer is not None
    assert answer["matched_key"] == "metric_income"
    assert "$669.700" in answer["answer"]


def test_versioned_articles_override_stale_database_copies(monkeypatch):
    from app.config import Settings
    from app.routes import assistant

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "key": "cashflow_structure",
                    "category": "finanzas",
                    "title": "Versión antigua",
                    "triggers": ["flujo"],
                    "response": "RESPUESTA OBSOLETA",
                    "follow_up": "",
                    "priority": 1,
                    "active": True,
                }
            ]

    monkeypatch.setattr(assistant.httpx, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(assistant.httpx, "post", lambda *args, **kwargs: Response())

    catalog = assistant._load_catalog(
        Settings(supabase_url="https://example.test", supabase_service_role_key="secret")
    )
    article = next(item for item in catalog if item["key"] == "cashflow_structure")

    assert "saldo inicial" in article["response"]
    assert "OBSOLETA" not in article["response"]
