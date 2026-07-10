"""Biblioteca de prompts de estandarización por rol (Fase 9).

Parsea `api/app/data/prompts_estandarizacion_por_rol.txt` en secciones y las
expone para las costuras de IA:

- ``system_prompt()``      → [PROMPT A]: system prompt de todos los llamados.
- ``classifier_prompt()``  → [PROMPT B]: clasificar una columna sin match en
                             el diccionario (fallback del mapeo universal).
- ``refine_prompt()``      → [PROMPT C]: revisión global de coherencia
                             (la interfaz de refine_with_ai, Fase 7 §5.13).
- ``prompt_for_role(rol)`` → el prompt del GRUPO al que pertenece el rol
                             (tiempo, dinero, cantidad, ... según el CSV).

Los prompts usan variables de plantilla ({COLUMNA}, {MUESTRA}, ...) que el
llamador reemplaza con ``fill()``. El archivo se parsea UNA vez (lazy).
"""

import re
import threading
from pathlib import Path

from .dictionary import role_group

_TXT_PATH = Path(__file__).resolve().parent.parent / "data" / "prompts_estandarizacion_por_rol.txt"

# grupo del CSV → encabezado de sección del TXT
_GROUP_SECTION = {
    "tiempo": "GRUPO 1",
    "dinero": "GRUPO 2",
    "cantidad": "GRUPO 3",
    "identificador": "GRUPO 4",
    "entidad": "GRUPO 5",
    "catalogo": "GRUPO 6",
    "ubicacion": "GRUPO 7",
    "contacto": "GRUPO 8",
    "clasificacion": "GRUPO 9",
    "texto_libre": "GRUPO 10",
    "rrhh": "GRUPO 11",
    "bancario": "GRUPO 12",
}

_SECTION_HEADER = re.compile(r"^\[(PROMPT [A-C]|GRUPO \d+)\b[^\]]*\]", re.MULTILINE)

_LOCK = threading.Lock()
_SECTIONS: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _SECTIONS
    if _SECTIONS is not None:
        return _SECTIONS
    with _LOCK:
        if _SECTIONS is not None:
            return _SECTIONS
        sections: dict[str, str] = {}
        if _TXT_PATH.exists():
            text = _TXT_PATH.read_text(encoding="utf-8")
            matches = list(_SECTION_HEADER.finditer(text))
            for i, match in enumerate(matches):
                key = match.group(1)
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                body = text[start:end]
                # Cortar en el borde de la siguiente sección (líneas de ═)
                body = re.sub(r"\n═+\s*$", "", body.strip("\n"), flags=re.MULTILINE).strip()
                sections[key] = body
        else:
            print(f"[prompt_library] No se encontró {_TXT_PATH}; los prompts IA no están disponibles.")
        _SECTIONS = sections
        return sections


def available_sections() -> list[str]:
    return sorted(_load().keys())


def system_prompt() -> str:
    return _load().get("PROMPT A", "")


def classifier_prompt() -> str:
    return _load().get("PROMPT B", "")


def refine_prompt() -> str:
    return _load().get("PROMPT C", "")


def prompt_for_role(rol: str) -> str:
    """Prompt del grupo al que pertenece el rol extendido ('' si no existe)."""
    grupo = role_group(rol)
    if not grupo:
        return ""
    return _load().get(_GROUP_SECTION.get(grupo, ""), "")


def fill(prompt: str, **variables: object) -> str:
    """Reemplaza variables de plantilla {NOMBRE} por su valor (str)."""
    result = prompt
    for name, value in variables.items():
        result = result.replace("{" + name.upper() + "}", str(value))
    return result
