"""Explain duplicate decisions without simulating unpublished corrected totals."""

from __future__ import annotations

import re
from typing import Any

from .language_normalization import normalize_basic, normalize_query


_DUPLICATES = re.compile(r"\b(?:duplicados?|(?:filas|registros|lineas) repetid[oa]s)\b")
_ANAPHORA = re.compile(r"\b(?:eso|esos|esas|los|las|mismo id|borrarlos|borralos|quitarlos|quitalos|eliminarlos|eliminalos|lo hiciste)\b")
_IMPACT = re.compile(r"\b(?:(?:cambi|afect|alter|infl|distorsion)(?:a|an|ar)|impacto|si los dejo|si los conservo)\b")
_REMOVE = re.compile(r"\b(?:sin duplicados?|quito|quitar|borrar|borro|elimino|eliminar|quitarlos|borrarlos|eliminarlos)\b")
_REVIEW = re.compile(r"\b(?:conviene|debo|deberia|recomiendas|compruebo|comprueban|reviso|verifico|distingo|identifico|basta)\b")
_ACTION = re.compile(r"^(?:y |por favor )?(?:borra|borralos|elimina|eliminalos|quita|quitalos|hazlo|ya lo hiciste|ya los borraste)\b")
_SUGGESTIONS = ["Como reviso los duplicados", "Calidad de los datos", "Descargar datos limpios"]
_REPLY_PREFIXES = (
    "el diagnostico publica", "no tengo un conteo valido de duplicados",
    "este chat no elimina filas", "no conviene borrar solo",
    "no tengo un diagnostico de duplicados",
)


def _intent(question: str) -> str | None:
    if _ACTION.search(question):
        return "action"
    if _REVIEW.search(question):
        return "review"
    if _IMPACT.search(question) or (
        _REMOVE.search(question)
        and re.search(r"\b(?:cuanto|cual|total|importe|ingresos|ventas|utilidad|margen|quedaria|seria)\b", question)
    ):
        return "impact"
    return None


def _previous_duplicate_topic(history: list[dict[str, Any]] | None) -> bool:
    active = False
    for row in (history or [])[-12:]:
        # Keep this response family across the bounded chat-history window.
        if row.get("role") == "assistant" and normalize_basic(row.get("content") or "").startswith(_REPLY_PREFIXES):
            active = True
        if row.get("role") != "user":
            continue
        question = normalize_query(row.get("content") or "")
        if _DUPLICATES.search(question):
            active = True
        elif not (active and _ANAPHORA.search(question) and _intent(question)):
            active = False
    return active


def conserved_duplicate_count(metrics: dict[str, Any]) -> int | None:
    from .metric_assistant import _number

    counts = metrics.get("duplicados")
    if not isinstance(counts, dict):
        return None

    def count(value: Any) -> int | None:
        number = _number(value)
        return int(number) if number is not None and number >= 0 and number.is_integer() else None

    # A published zero is authoritative; an unknown value is not zero.
    if "conservados" in counts:
        return count(counts["conservados"])
    detected, removed = count(counts.get("detectados")), count(counts.get("eliminados"))
    if detected is not None and removed is not None and detected >= removed:
        return detected - removed
    return None


def answer_duplicate_impact(
    question: str, metrics: dict[str, Any], history: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    from .assistant_queries import _measure, _scope_parts
    from .metric_assistant import _collection_dashboard, _result

    intent = _intent(question)
    explicit = bool(_DUPLICATES.search(question))
    followup = _ANAPHORA.search(question) or (
        intent is None and question.startswith("y ") and not _measure(question)
    )
    if not (explicit or (followup and _previous_duplicate_topic(history))):
        return None
    if intent == "action":
        return _result(
            "Este chat no elimina filas ni cambia tu archivo. Revisa los grupos en Limpieza "
            "y confirma alli la decision sobre duplicados. Un ID repetido con datos distintos "
            "es un conflicto que debe revisarse, no una orden de borrado.",
            "metric_duplicate_action", _SUGGESTIONS,
        )
    if intent == "review":
        return _result(
            "No conviene borrar solo porque dos filas se parecen. Compara el ID del documento "
            "y de la linea, fecha, producto, cantidad, importe y estado con la fuente. "
            "El mismo ID con datos distintos es un conflicto; varias lineas de una factura "
            "pueden ser legitimas. Confirma repeticiones exactas en Limpieza y compara el "
            "resultado antes de descargar. El chat no modifica el archivo.",
            "metric_duplicate_review", _SUGGESTIONS, "medium",
        )
    scope_question = re.sub(r"\bsin duplicados?\b", "", question)
    period, segment = _scope_parts(scope_question, metrics)
    if period or segment or re.search(r"\b(?:hoy|ayer|semana|trimestre|semestre|mes pasado|mes anterior)\b", question):
        return _result(
            "No tengo un diagnostico de duplicados ni un total corregido publicado para "
            "ese periodo o segmento. El conteo general no lo sustituye. Revisa las filas "
            "que entran en ese alcance y compara el calculo con la decision confirmada en Limpieza.",
            "metric_duplicate_scope", _SUGGESTIONS, "medium",
        )
    if not intent:
        return None
    # The existing collection answer additionally documents missing payment IDs.
    if _collection_dashboard(metrics) is not None and "sin duplicados" in question:
        return None
    conserved = conserved_duplicate_count(metrics)
    if conserved is None:
        intro = "No tengo un conteo valido de duplicados conservados; eso no significa cero. "
    elif conserved == 0:
        intro = "El diagnostico publica 0 duplicados conservados. No atribuyo una diferencia a filas que no aparecen conservadas. "
    else:
        label = "duplicado conservado" if conserved == 1 else "duplicados conservados"
        intro = f"El diagnostico publica {conserved} {label}. "
    return _result(
        intro + "Pueden afectar los importes si esas filas entran en el indicador. No tengo "
        "calculado el total sin ellas: un conteo de filas no equivale a un importe. "
        "El efecto depende de sus montos, signos y filtros; quitar una devolucion negativa "
        "incluso puede aumentar el total. Revisa los grupos antes de confirmar una eliminacion.",
        "metric_duplicate_impact", _SUGGESTIONS, "medium",
    )
