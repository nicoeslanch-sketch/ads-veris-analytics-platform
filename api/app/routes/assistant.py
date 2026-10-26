"""Asistente gratuito determinista y configuracion del chat avanzado."""

import json
import math
from collections import defaultdict, deque
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator

from ..auth import AuthenticatedUser, get_current_user
from ..config import Settings, get_settings
from ..support_knowledge import ARTICLES, answer_for
from ..relationship_assistant import RelationshipContext
from ..request_budget import consume_budget

router = APIRouter(prefix="/assistant")
_TIMEOUT = 10
_requests: dict[str, deque[datetime]] = defaultdict(deque)
_request_lock = Lock()
_catalog_lock = Lock()
_catalog_refresh_lock = Lock()
_catalog_cache: OrderedDict[tuple[str, str], tuple[float, list[dict]]] = OrderedDict()
_last_rate_sweep = 0.0


class BotMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class BotRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1200)
    metrics: dict | None = None
    relationship_dashboard: RelationshipContext | None = None
    historial: list[BotMessage] = Field(default_factory=list, max_length=12)

    @field_validator("message")
    @classmethod
    def require_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Escribe una pregunta.")
        return value.strip()

    @field_validator("metrics")
    @classmethod
    def bounded_context(cls, value: dict | None) -> dict | None:
        if value is None:
            return value
        stack = [(value, 0)]
        count = 0
        while stack:
            node, depth = stack.pop()
            count += 1
            if depth > 18 or count > 20000:
                raise ValueError("El contexto de metricas excede la estructura permitida.")
            if isinstance(node, str) and len(node) > 4000:
                raise ValueError('Un texto del contexto excede el limite permitido.')
            if isinstance(node, float) and not math.isfinite(node):
                raise ValueError('Los indicadores deben contener numeros finitos.')
            if isinstance(node, dict):
                if any(len(str(key)) > 256 for key in node):
                    raise ValueError('Una clave del contexto excede el limite permitido.')
                stack.extend((child, depth + 1) for child in node.values())
            elif isinstance(node, list):
                stack.extend((child, depth + 1) for child in node)
        for key in ("kpis", "periodo", "duplicados", "clientes", "proyeccion", "analisis_negocio", "analisis_generico", "analisis_inventario", "analisis_campanas", "analisis_productos", "indicadores_financieros", "moneda_detalle", "matriz_mes_dimension"):
            if value.get(key) is not None and not isinstance(value[key], dict):
                raise ValueError(f"{key} debe ser un objeto de indicadores.")
        for key in ("evolucion_mensual", "top_productos", "ventas_por_canal", "por_categoria", "agrupaciones_flexibles"):
            if value.get(key) is not None and (not isinstance(value[key], list) or not all(isinstance(row, dict) for row in value[key])):
                raise ValueError(f"{key} debe ser una lista de indicadores.")
        # Validate containers that the deterministic readers traverse, without
        # coercing missing values to zero or discarding unfamiliar metric fields.
        object_paths = (
            "patrones_productos", "actividad_productos", "analisis_negocio.conciliacion.patrones_productos",
            "kpis.cobertura_costos", "kpis.devoluciones", "kpis.unidades_detalle", "analisis_generico.evolucion",
            "analisis_negocio.cobranza", "analisis_negocio.estado_resultados", "analisis_negocio.filtros", "analisis_negocio.filtros.aplicados",
            "analisis_negocio.cobranza.kpis", "analisis_negocio.cobranza.periodo",
            "analisis_negocio.cobranza.comparacion", "analisis_productos.costos",
            "analisis_productos.precios_lista", "analisis_productos.margen_potencial", "indicadores_financieros.items",
            "analisis_negocio.catalogo_indicadores",
            "analisis_negocio.conciliacion", "analisis_negocio.conciliacion.kpis", "analisis_negocio.conciliacion.periodo",
        )
        list_paths = (
            "actividad_productos.productos", "patrones_productos.series", "patrones_productos.picos_recurrentes",
            "analisis_negocio.conciliacion.patrones_productos.series", "analisis_negocio.conciliacion.patrones_productos.picos_recurrentes",
            "clientes.top", "por_dia_semana", "analisis_negocio.ratios", "matriz_mes_dimension.valores",
            "analisis_generico.numericas", "analisis_generico.desgloses", "analisis_generico.distribuciones",
            "analisis_generico.evolucion.valores", "analisis_inventario.por_sucursal",
            "analisis_negocio.cobranza.equipos", "analisis_negocio.cobranza.agencias",
            "analisis_negocio.cobranza.formas_pago", "analisis_negocio.cobranza.periodos_cotizados",
            "analisis_negocio.cobranza.evolucion",
            "analisis_negocio.catalogo_indicadores.categorias",
            "analisis_negocio.conciliacion.mensual", "analisis_negocio.conciliacion.productos",
            "analisis_negocio.conciliacion.categorias", "analisis_negocio.conciliacion.sucursales",
            "analisis_negocio.conciliacion.inventario_lento",
        )
        for path in (*object_paths, *list_paths):
            node = value
            for part in path.split('.'):
                node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                continue
            valid = isinstance(node, dict) if path in object_paths else isinstance(node, list) and all(isinstance(row, dict) for row in node)
            if not valid:
                raise ValueError(f"Estructura de indicadores invalida: {path}.")
        for rows, keys in (
            ((value.get('patrones_productos') or {}).get('series') or [], ('valores',)),
            ((value.get('patrones_productos') or {}).get('picos_recurrentes') or [], ('evidencia',)),
            ((((value.get('analisis_negocio') or {}).get('conciliacion') or {}).get('patrones_productos') or {}).get('series') or [], ('valores',)),
            ((((value.get('analisis_negocio') or {}).get('conciliacion') or {}).get('patrones_productos') or {}).get('picos_recurrentes') or [], ('evidencia',)),
            (value.get("agrupaciones_flexibles") or [], ("grupos", "grupos_completos")),
            ((value.get("analisis_generico") or {}).get("desgloses") or [], ("valores",)),
            ((value.get("analisis_generico") or {}).get("distribuciones") or [], ("valores",)),
        ):
            for row in rows:
                for key in keys:
                    if row.get(key) is not None and (not isinstance(row[key], list) or not all(isinstance(item, dict) for item in row[key])):
                        raise ValueError(f"{key} debe ser una lista de indicadores.")
        catalog = (value.get('analisis_negocio') or {}).get('catalogo_indicadores') or {}
        for category in catalog.get('categorias') or []:
            indicators = category.get('indicadores')
            if indicators is None:
                continue
            if not isinstance(indicators, list) or not all(isinstance(item, dict) for item in indicators):
                raise ValueError('indicadores debe ser una lista de objetos.')
            for item in indicators:
                for key in ('advertencias', 'fuentes'):
                    entries = item.get(key)
                    if entries is not None and (not isinstance(entries, list) or not all(isinstance(entry, str) for entry in entries)):
                        raise ValueError(f'{key} debe ser una lista de textos.')
        return value


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }


def _rest(settings: Settings, table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


def _guard_rate(user_id: str) -> None:
    global _last_rate_sweep
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=1)
    with _request_lock:
        if monotonic() - _last_rate_sweep >= 60:
            stale = [key for key, queue in _requests.items() if not queue or queue[-1] < cutoff]
            for key in stale:
                del _requests[key]
            _last_rate_sweep = monotonic()
        entries = _requests[user_id]
        while entries and entries[0] < cutoff:
            entries.popleft()
        if len(entries) >= 20:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Enviaste muchas preguntas seguidas. Espera un minuto y vuelve a intentar.",
                headers={"Retry-After": "60"},
            )
        entries.append(now)


def _load_catalog(settings: Settings) -> list[dict]:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return ARTICLES
    try:
        response = httpx.get(
            _rest(settings, "support_bot_articles"),
            params={
                "active": "eq.true",
                "select": "key,category,title,triggers,response,follow_up,priority,active",
                "order": "priority.desc",
                "limit": "500",
            },
            headers=_headers(settings),
            timeout=3,
        )
        response.raise_for_status()
        rows = response.json()
        if rows:
            rows_by_key = {str(row.get("key")): row for row in rows}
            # Las respuestas versionadas son la fuente canonica para evitar que
            # una copia antigua en la base tape correcciones ya desplegadas. La
            # base puede seguir agregando articulos con claves propias.
            merged = dict(rows_by_key)
            merged.update({str(item.get("key")): item for item in ARTICLES})
            return sorted(
                merged.values(),
                key=lambda item: int(item.get("priority") or 0),
                reverse=True,
            )
        # Answering a question is read-only. Catalog writes belong to admin setup.
        return ARTICLES
    except httpx.HTTPError:
        return ARTICLES


def _cached_catalog(settings: Settings) -> list[dict]:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return ARTICLES
    key = (settings.supabase_url, settings.supabase_service_role_key)
    with _catalog_lock:
        cached = _catalog_cache.get(key)
        if cached and cached[0] > monotonic():
            _catalog_cache.move_to_end(key)
            return cached[1]
    if not _catalog_refresh_lock.acquire(blocking=False):
        return cached[1] if cached else ARTICLES
    try:
        rows = _load_catalog(settings)
        with _catalog_lock:
            _catalog_cache[key] = (monotonic() + 120, rows)
            _catalog_cache.move_to_end(key)
            while len(_catalog_cache) > 4:
                _catalog_cache.popitem(last=False)
        return rows
    finally:
        _catalog_refresh_lock.release()


@router.get("/config")
async def assistant_config(
    _: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    return {
        "quick_help_enabled": True,
        "advanced_enabled": settings.advanced_ai_enabled,
        "advanced_message_cost": settings.ads_coins_advanced_message_cost,
        "purchases_enabled": settings.ads_coin_purchases_enabled,
        "knowledge_articles": len(ARTICLES),
    }


@router.post("/bot")
async def ask_quick_help(
    body: BotRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    if settings.supabase_url and settings.supabase_service_role_key:
        await run_in_threadpool(consume_budget, 'assistant:' + user.id, settings, limit=20, window=60)
    else:
        _guard_rate(user.id)
    if body.metrics is not None and len(json.dumps(body.metrics)) > 200_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El contexto de métricas es demasiado grande.",
        )
    history = [item.model_dump(mode="json") for item in body.historial]
    context = ({'relationship_dashboard': body.relationship_dashboard.model_dump()}
               if body.relationship_dashboard is not None else body.metrics)
    result = await run_in_threadpool(answer_for, body.message, ARTICLES, context, history)
    catalog = ARTICLES
    # Published metrics and conversation control do not depend on a database read.
    if result.get('confidence') != 'high' and not str(result.get("matched_key") or "").startswith(("metric_", "conversation_", "greeting")):
        catalog = await run_in_threadpool(_cached_catalog, settings)
        if catalog is not ARTICLES:
            result = await run_in_threadpool(answer_for, body.message, catalog, context, history)
    return {
        **result,
        "mode": "deterministic",
        "coins_charged": 0,
        "knowledge_articles": len(catalog),
    }
