"""Endpoints del Asistente IA (SPEC §8). Requieren JWT de Supabase.

POST /ai/summary — genera resumen automático + preguntas sugeridas a partir del
                   MetricsResult del dashboard. Respuesta JSON completa.

POST /ai/chat    — responde preguntas libres ancladas a los datos del negocio.
                   Devuelve SSE (text/event-stream) para que el texto aparezca
                   progresivamente en el panel.

Las llamadas a la Anthropic API ocurren EXCLUSIVAMENTE aquí: nunca en el
frontend. La API key vive solo en la variable de entorno ANTHROPIC_API_KEY.
"""

import json

from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import get_current_user
from ..config import Settings, get_settings

router = APIRouter(prefix="/ai", dependencies=[Depends(get_current_user)])

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# ── System prompt ────────────────────────────────────────────────────────────

_SYSTEM = (
    "Eres un analista de datos experto que trabaja con PyMEs chilenas. "
    "Tu trabajo es interpretar los datos de ventas y finanzas del negocio y entregar "
    "recomendaciones concretas, directas y accionables. "
    "No te limites a describir los números: explica qué significan para el negocio "
    "y qué debería hacer el dueño al respecto. "
    "Responde siempre en español de Chile. Sé conciso: máximo 3-4 párrafos. "
    "Usa moneda CLP (pesos chilenos) con formato $1.234.000. "
    "Nunca inventes datos que no estén en el contexto entregado."
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _client(settings: Settings) -> AsyncAnthropic:
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Asistente IA no disponible: falta ANTHROPIC_API_KEY en el servidor.",
        )
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _model(settings: Settings) -> str:
    return settings.anthropic_model or _DEFAULT_MODEL


def _metrics_context(metrics: dict) -> str:
    """Serializa el MetricsResult a un texto compacto para el prompt."""
    parts: list[str] = []

    periodo = metrics.get("periodo", {})
    if periodo.get("desde") or periodo.get("hasta"):
        parts.append(f"Período analizado: {periodo.get('desde', '?')} → {periodo.get('hasta', '?')}")

    kpis = metrics.get("kpis", {})
    moneda = metrics.get("moneda", "CLP")

    def fmt(v):
        if v is None:
            return "N/D"
        try:
            return f"${int(v):,}".replace(",", ".")
        except Exception:
            return str(v)

    def kpi_line(label: str, kpi: dict | None) -> str:
        if not kpi:
            return f"{label}: N/D"
        val = fmt(kpi.get("valor"))
        var = kpi.get("variacion_pct")
        var_str = f" (var. {var:+.1f}%)" if var is not None else ""
        return f"{label}: {val}{var_str}"

    parts.append(kpi_line("Ingresos totales", kpis.get("ingresos_totales")))
    if kpis.get("gastos_totales"):
        parts.append(kpi_line("Gastos totales", kpis["gastos_totales"]))
    if kpis.get("ganancia_neta"):
        parts.append(kpi_line("Ganancia neta", kpis["ganancia_neta"]))
    if kpis.get("margen_utilidad_pct"):
        val = kpis["margen_utilidad_pct"].get("valor")
        parts.append(f"Margen de utilidad: {val:.1f}%" if val is not None else "Margen de utilidad: N/D")
    parts.append(f"Transacciones: {kpis.get('transacciones', 'N/D')}")
    if kpis.get("ticket_promedio"):
        parts.append(f"Ticket promedio: {fmt(kpis['ticket_promedio'])}")

    evolucion = metrics.get("evolucion_mensual", [])
    if evolucion:
        meses_str = ", ".join(
            f"{e['mes']} ingresos={fmt(e['ingresos'])}" for e in evolucion[-6:]
        )
        parts.append(f"Evolución últimos meses: {meses_str}")

    top = metrics.get("top_productos", [])
    if top:
        top_str = ", ".join(f"{p['nombre']} ({fmt(p['ingresos'])})" for p in top[:5])
        parts.append(f"Top productos/servicios: {top_str}")

    canales = metrics.get("ventas_por_canal", [])
    if canales:
        canales_str = ", ".join(f"{c['nombre']} {c['porcentaje']:.1f}%" for c in canales[:5])
        parts.append(f"Ventas por canal/sucursal: {canales_str}")

    categorias = metrics.get("por_categoria", [])
    if categorias:
        cat_str = ", ".join(f"{c['nombre']} ({fmt(c['ingresos'])})" for c in categorias[:5])
        parts.append(f"Categorías principales: {cat_str}")

    proyeccion = metrics.get("proyeccion")
    if proyeccion:
        crecim = proyeccion.get("crecimiento_pct", 0)
        parts.append(f"Proyección tendencia: {crecim:+.1f}% mensual estimado")

    advertencias = metrics.get("advertencias", [])
    if advertencias:
        parts.append("Advertencias del motor: " + "; ".join(advertencias))

    return "\n".join(parts)


# ── Modelos de request ────────────────────────────────────────────────────────


class SummaryRequest(BaseModel):
    metrics: dict


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    pregunta: str
    metrics: dict
    historial: list[ChatMessage] = []


class RecommendationRequest(BaseModel):
    metrics: dict
    hallazgos: list[str] = []
    analisis: str = ""  # descripción del análisis activo (ej: "ingresos por categoría, mayo")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/summary")
async def ai_summary(
    body: SummaryRequest,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Genera resumen automático del negocio + preguntas sugeridas."""
    try:
        ctx = _metrics_context(body.metrics)
        prompt = (
            f"Aquí están los datos del negocio:\n\n{ctx}\n\n"
            "Redacta un resumen ejecutivo del periodo: qué pasó, qué es destacable "
            "(positivo o negativo) y cuál es la recomendación principal. "
            "Luego, en una línea separada que empiece exactamente con 'SUGERENCIAS:', "
            "lista 4 preguntas cortas que el dueño podría querer hacerte, separadas por '|'. "
            "Ejemplo: SUGERENCIAS: ¿Cuál es el mes más fuerte?|¿Qué producto debo potenciar?|..."
        )
        client = _client(settings)
        response = await client.messages.create(
            model=_model(settings),
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except HTTPException:
        raise
    except APIConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo conectar con el servicio de IA: {exc}",
        ) from exc
    except APIStatusError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"Error del servicio de IA ({exc.status_code}): {exc.message}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del asistente: {exc}",
        ) from exc

    full_text: str = response.content[0].text  # type: ignore[index]

    resumen = full_text
    sugerencias: list[str] = []

    if "SUGERENCIAS:" in full_text:
        parts = full_text.split("SUGERENCIAS:", 1)
        resumen = parts[0].strip()
        raw_sugs = parts[1].strip()
        sugerencias = [s.strip() for s in raw_sugs.split("|") if s.strip()][:4]

    if not sugerencias:
        sugerencias = [
            "¿Cuál fue el mes con más ventas?",
            "¿Qué producto o servicio es el más rentable?",
            "¿Cómo está el margen de utilidad?",
            "¿Qué debería priorizar el próximo mes?",
        ]

    return {"resumen": resumen, "sugerencias": sugerencias}


@router.post("/recommendation")
async def ai_recommendation(
    body: RecommendationRequest,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Recomendación inteligente de Explorar datos (SPEC §7): lectura del
    análisis activo + plan de acción concreto. Se genera solo a pedido del
    usuario (botón), nunca automáticamente — control de costo de IA."""
    try:
        ctx = _metrics_context(body.metrics)
        hallazgos_txt = "\n".join(f"- {h}" for h in body.hallazgos[:8])
        prompt = (
            f"Aquí están los datos del negocio:\n\n{ctx}\n\n"
            + (f"Análisis que el usuario está mirando: {body.analisis}\n\n" if body.analisis else "")
            + (f"Hallazgos ya detectados:\n{hallazgos_txt}\n\n" if hallazgos_txt else "")
            + "Entrega UNA recomendación principal para el negocio (2-3 frases, "
            "directa y accionable, no repitas los hallazgos: interprétalos). "
            "Luego, en una línea separada que empiece exactamente con 'PLAN:', "
            "lista 3 pasos concretos de acción separados por '|'. "
            "Ejemplo: PLAN: Renegocia el precio de X|Concentra promoción en el canal Y|Revisa el stock de Z"
        )
        client = _client(settings)
        response = await client.messages.create(
            model=_model(settings),
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except HTTPException:
        raise
    except APIConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo conectar con el servicio de IA: {exc}",
        ) from exc
    except APIStatusError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"Error del servicio de IA ({exc.status_code}): {exc.message}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del asistente: {exc}",
        ) from exc

    full_text: str = response.content[0].text  # type: ignore[index]

    recomendacion = full_text
    plan: list[str] = []
    if "PLAN:" in full_text:
        parts = full_text.split("PLAN:", 1)
        recomendacion = parts[0].strip()
        plan = [p.strip() for p in parts[1].strip().split("|") if p.strip()][:3]

    return {"recomendacion": recomendacion, "plan": plan}


@router.post("/chat")
async def ai_chat(
    body: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Chat libre anclado a los datos del negocio. Devuelve SSE."""
    ctx = _metrics_context(body.metrics)

    messages: list[dict] = []

    # Contexto inicial siempre como primer turno de usuario
    messages.append({
        "role": "user",
        "content": f"Contexto del negocio para esta sesión:\n\n{ctx}",
    })
    messages.append({
        "role": "assistant",
        "content": "Entendido. Tengo el contexto del negocio. ¿Qué quieres saber?",
    })

    # Historial previo de la conversación (últimas 6 exchanges)
    for msg in body.historial[-12:]:
        messages.append({"role": msg.role, "content": msg.content})

    # Pregunta actual
    messages.append({"role": "user", "content": body.pregunta})

    client = _client(settings)

    async def generate():
        try:
            async with client.messages.stream(
                model=_model(settings),
                max_tokens=1024,
                system=_SYSTEM,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield f"data: {json.dumps({'chunk': text})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
